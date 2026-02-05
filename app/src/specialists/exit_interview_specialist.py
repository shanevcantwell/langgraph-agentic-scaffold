# app/src/specialists/exit_interview_specialist.py
"""
Exit Interview Specialist - ADR-ROADMAP-001 Phase 1

Gates the END node by validating that the accumulated state actually satisfies
the user's original request. This prevents premature termination when Router
decides to end but the task isn't truly complete.

Flow:
    Router decides END → exit_interview_specialist → {complete → END, incomplete → Router}

Uses InferenceService (via MCP or direct call) for LLM-backed completion evaluation.
"""

import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from .schemas import ReturnControlMode
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


class CompletionEvaluation(BaseModel):
    """Structured output for completion evaluation."""
    is_complete: bool = Field(..., description="Whether the task is complete")
    reasoning: str = Field(..., description="Brief explanation of the evaluation")
    missing_elements: str = Field(
        default="",
        description="What's still needed if incomplete (empty if complete)"
    )
    recommended_specialists: List[str] = Field(
        default_factory=list,
        description="Which specialist(s) should handle the missing work (e.g., ['project_director'] for file operations)"
    )
    return_control: ReturnControlMode = Field(
        default=ReturnControlMode.ACCUMULATE,
        description=(
            "How the Facilitator should handle context on retry: "
            "'accumulate' (default) to append new work to history, "
            "'reset' to clear context and start over (if polluted), "
            "'delta' to run a NEW plan for just the missing elements"
        )
    )


class ExitInterviewSpecialist(BaseSpecialist):
    """
    Validates task completion before allowing workflow to terminate.

    This specialist acts as a gate before END, evaluating whether the accumulated
    state (artifacts, messages, context_plan) satisfies the original user request.

    If complete: Sets task_is_complete=True, allowing standard edge to route to END
    If incomplete: Does NOT set task_is_complete, causing route back to Router

    See ADR-ROADMAP-001 Phase 1 for architectural details.
    """

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Evaluate if the task is semantically complete.

        ADR-CORE-061: Exit Interview is now a PURE LLM semantic evaluator.
        All infrastructure heuristics (max_iterations, trace stutter, failures)
        have been moved to the Interrupt Classifier (graph_orchestrator.py).

        Exit Interview answers ONE question: "Is the task done?"
        It evaluates:
        1. Original user_request (from artifacts)
        2. Current context_plan (Triage's assessment)
        3. Accumulated artifacts and recent messages
        4. LLM judgment: "Can we give a satisfying response to the user?"
        """
        artifacts = state.get("artifacts", {})
        messages = state.get("messages", [])

        # Get original user request
        user_request = artifacts.get("user_request", "")
        if not user_request and messages:
            # Fallback: extract from first user message
            for msg in messages:
                if hasattr(msg, 'type') and msg.type == 'human':
                    user_request = msg.content
                    break
                elif hasattr(msg, 'content') and not hasattr(msg, 'type'):
                    # First message is likely the user request
                    user_request = msg.content
                    break

        # Get context_plan if available (Triage's assessment)
        context_plan = artifacts.get("context_plan", {})
        recommended_specialists = context_plan.get("recommended_specialists", [])

        # Get routing history to see what has executed
        routing_history = state.get("routing_history", [])

        # Issue #115: Lazy initialization of exit_plan via SA MCP tool
        # EI is graph-wired, can't use requires_artifacts. Call SA on-demand.
        exit_plan = artifacts.get("exit_plan", {})
        if not exit_plan and self.mcp_client:
            logger.info("ExitInterviewSpecialist: No exit_plan found, calling SA via MCP")
            try:
                result = self.mcp_client.call(
                    "systems_architect",
                    "create_plan",
                    context=user_request,
                    artifact_key="exit_plan"
                )
                exit_plan = result.get("artifacts", {}).get("exit_plan", {})
                logger.info(f"ExitInterviewSpecialist: SA produced exit_plan: {exit_plan.get('plan_summary', '?')}")
            except Exception as e:
                logger.warning(f"ExitInterviewSpecialist: SA MCP call failed: {e}")
                exit_plan = {}  # Proceed without - EI handles missing gracefully
        elif exit_plan:
            logger.info(f"ExitInterviewSpecialist: Using existing exit_plan for verification")

        # Build artifact summary (excluding internal/large artifacts)
        artifact_keys = [k for k in artifacts.keys()
                        if not k.startswith("_") and k not in ("gathered_context", "context_plan")]

        # Get recent messages (last 5) for context
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        recent_summary = self._summarize_messages(recent_messages)

        logger.info(
            f"ExitInterviewSpecialist evaluating completion: "
            f"artifacts={artifact_keys}, routing_history={routing_history[-3:]}"
        )

        # Evaluate completion using LLM
        evaluation = self._evaluate_completion(
            user_request=user_request,
            exit_plan=exit_plan,
            recommended_specialists=recommended_specialists,
            routing_history=routing_history,
            artifact_keys=artifact_keys,
            recent_summary=recent_summary
        )

        if evaluation.is_complete:
            logger.info(
                f"ExitInterviewSpecialist: Task COMPLETE - {evaluation.reasoning}"
            )
            return {
                "messages": [AIMessage(content=f"[Exit Interview] Task verified complete: {evaluation.reasoning}")],
                "task_is_complete": True,
                "artifacts": {
                    "exit_plan": exit_plan,  # Issue #115: Persist for archive/observability
                    "max_iterations_exceeded": False,  # Consumed - no meaning after Exit Interview
                    "exit_interview_result": {
                        "is_complete": True,
                        "reasoning": evaluation.reasoning
                    }
                }
            }
        else:
            # Use recommended_specialists from LLM, default to project_director if empty
            recommended = evaluation.recommended_specialists or ["project_director"]
            logger.info(
                f"ExitInterviewSpecialist: Task INCOMPLETE - {evaluation.reasoning}. "
                f"Missing: {evaluation.missing_elements}. Recommended: {recommended}"
            )

            # Build message that Router will respect
            # Router's prompt says to respect "**Dependency Requirement:**" messages
            specialists_str = ", ".join(recommended)
            guidance_msg = (
                f"[Exit Interview] Task not complete: {evaluation.reasoning}\n\n"
                f"**Dependency Requirement:** The following work is still needed: {evaluation.missing_elements}. "
                f"Route to one of: `{specialists_str}` to complete this work."
            )

            return {
                "messages": [AIMessage(content=guidance_msg)],
                # CRITICAL: Explicitly set task_is_complete=False to override any earlier
                # specialist's claim. GraphState merges (doesn't replace), so omitting
                # this would leave the stale True value from a prior specialist.
                "task_is_complete": False,
                "artifacts": {
                    "exit_plan": exit_plan,  # Issue #115: Persist for next iteration
                    "max_iterations_exceeded": False,  # Consumed - no meaning after Exit Interview
                    "exit_interview_result": {
                        "is_complete": False,
                        "reasoning": evaluation.reasoning,
                        "missing_elements": evaluation.missing_elements,
                        "recommended_specialists": recommended,
                        "return_control": evaluation.return_control.value
                    }
                },
                "scratchpad": {
                    # Signal to Router which specialist to try next
                    # Aligned with Triage's ContextPlan pattern - same signal, no translation
                    "recommended_specialists": recommended,
                    "exit_interview_incomplete": True
                }
            }

    def _evaluate_completion(
        self,
        user_request: str,
        exit_plan: dict,
        recommended_specialists: list,
        routing_history: list,
        artifact_keys: list,
        recent_summary: str
    ) -> CompletionEvaluation:
        """
        Use LLM to evaluate if the task is complete.

        This is the core judgment: given what was requested and what has been done,
        can we provide a satisfying response to the user?

        ADR-CORE-063: Now includes exit_plan (mapped from system_plan) for verification
        against success criteria.
        """
        if not self.llm_adapter:
            logger.warning("ExitInterviewSpecialist: No LLM adapter, defaulting to complete")
            return CompletionEvaluation(
                is_complete=True,
                reasoning="No LLM adapter available for evaluation - defaulting to complete",
                missing_elements=""
            )

        # Try to load the prompt template, fall back to inline prompt if not found
        try:
            prompt_template = load_prompt("exit_interview_prompt.md")
        except (FileNotFoundError, IOError):
            prompt_template = self._get_default_prompt()

        # Format exit_plan for prompt (extract key fields)
        if exit_plan:
            exit_plan_summary = self._format_exit_plan(exit_plan)
        else:
            exit_plan_summary = "[No exit plan available - verify based on user request only]"

        # Format the prompt with current state
        prompt = prompt_template.format(
            user_request=user_request or "[Unable to extract original request]",
            exit_plan=exit_plan_summary,
            recommended_specialists=", ".join(recommended_specialists) if recommended_specialists else "[No specific recommendations]",
            routing_history=", ".join(routing_history[-10:]) if routing_history else "[No routing history]",
            artifact_keys=", ".join(artifact_keys) if artifact_keys else "[No artifacts produced]",
            recent_summary=recent_summary or "[No recent activity]"
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=CompletionEvaluation
        )

        try:
            response = self.llm_adapter.invoke(request)
            json_response = response.get("json_response", {})

            if json_response:
                return CompletionEvaluation(**json_response)
            else:
                # Parse from content if structured output failed
                logger.warning("ExitInterviewSpecialist: Structured output failed, defaulting to complete")
                return CompletionEvaluation(
                    is_complete=True,
                    reasoning="Could not parse LLM response - defaulting to complete to avoid loops",
                    missing_elements=""
                )
        except Exception as e:
            logger.error(f"ExitInterviewSpecialist: LLM evaluation failed: {e}")
            return CompletionEvaluation(
                is_complete=True,
                reasoning=f"Evaluation error ({e}) - defaulting to complete to avoid loops",
                missing_elements=""
            )

    def _summarize_messages(self, messages: list) -> str:
        """Create a brief summary of recent messages for the evaluation prompt."""
        summaries = []
        for msg in messages:
            msg_type = getattr(msg, 'type', 'unknown')
            content = getattr(msg, 'content', str(msg))
            summaries.append(f"[{msg_type}]: {content}")
        return "\n".join(summaries)

    def _format_exit_plan(self, exit_plan: dict) -> str:
        """
        Format the exit_plan artifact for the evaluation prompt.

        ADR-CORE-063: Extract success criteria and key plan details for verification.
        """
        parts = []

        # Extract plan summary if available
        if "plan_summary" in exit_plan:
            parts.append(f"**Plan Summary:** {exit_plan['plan_summary']}")

        # Extract success criteria (the key field for verification)
        if "success_criteria" in exit_plan:
            parts.append(f"**Success Criteria:** {exit_plan['success_criteria']}")

        # Extract steps if available
        if "steps" in exit_plan:
            steps = exit_plan["steps"]
            if isinstance(steps, list):
                steps_str = "\n".join(f"  - {s}" for s in steps[:10])  # Limit to 10 steps
                parts.append(f"**Planned Steps:**\n{steps_str}")

        # Extract expected artifacts if available
        if "expected_artifacts" in exit_plan:
            parts.append(f"**Expected Artifacts:** {exit_plan['expected_artifacts']}")

        # If no structured fields, dump the whole thing
        if not parts:
            import json
            try:
                parts.append(f"**Full Plan:**\n{json.dumps(exit_plan, indent=2, default=str)[:2000]}")
            except (TypeError, ValueError):
                parts.append(f"**Full Plan:** {str(exit_plan)[:2000]}")

        return "\n\n".join(parts)

    def _get_default_prompt(self) -> str:
        """Default prompt if exit_interview_prompt.md is not found."""
        return """You are evaluating whether a task is complete.

**Original User Request:**
{user_request}

**Exit Plan (Success Criteria):**
{exit_plan}

**Planned Actions (from Triage):**
{recommended_specialists}

**What Has Executed:**
{routing_history}

**Current Artifacts:**
{artifact_keys}

**Recent Activity:**
{recent_summary}

**Question:** Based on the above, can we provide a satisfying response to the user's original request?

Evaluate whether:
1. The user's core request has been addressed
2. If an exit plan with success criteria exists, have those criteria been met?
3. If specialists were recommended, have the appropriate ones executed?
4. Are there meaningful artifacts or responses that answer the request?

**IMPORTANT:** Do NOT trust claims of completed work in messages. If the exit plan specifies file operations, you should use your `list_directory` tool to VERIFY the filesystem state matches the success criteria.

Be CONSERVATIVE: If in doubt, mark as INCOMPLETE to give the system another chance.
The only cost of being conservative is one more routing cycle.
The cost of premature completion is an unsatisfied user.

Return your evaluation as JSON with:
- is_complete: boolean
- reasoning: brief explanation (1-2 sentences)
- missing_elements: what's still needed if incomplete (empty string if complete)
- recommended_specialists: list of specialist(s) that should handle the missing work (e.g., ["project_director"] for file operations)
"""
