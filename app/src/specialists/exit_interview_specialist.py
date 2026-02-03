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
        Evaluate if the task is complete before routing to END.

        Checks (in order):
        1. ADR-CORE-058 Phase 1: Mechanical heuristics (no LLM needed)
           - max_iterations_exceeded artifact
           - Failed operations in research_trace with no recovery
        2. Original user_request (from artifacts)
        3. Current context_plan (Triage's assessment)
        4. Accumulated artifacts and recent messages
        5. LLM judgment: "Can we give a satisfying response to the user?"
        """
        artifacts = state.get("artifacts", {})
        messages = state.get("messages", [])

        # ADR-CORE-058 Phase 1: Mechanical heuristics first (no LLM call)
        heuristic_result = self._evaluate_trace_heuristics(artifacts)
        if heuristic_result:
            # Obvious failure detected - return early without LLM call
            if heuristic_result.is_complete:
                # Heuristics said complete (shouldn't happen in Phase 1, but handle it)
                return {
                    "messages": [AIMessage(content=f"[Exit Interview] Task verified complete: {heuristic_result.reasoning}")],
                    "task_is_complete": True,
                    "artifacts": {
                        "exit_interview_result": {
                            "is_complete": True,
                            "reasoning": heuristic_result.reasoning,
                            "method": "heuristic"
                        }
                    }
                }
            else:
                # Heuristics detected failure
                recommended = heuristic_result.recommended_specialists or ["project_director"]
                specialists_str = ", ".join(recommended)
                guidance_msg = (
                    f"[Exit Interview] Task not complete (heuristic): {heuristic_result.reasoning}\n\n"
                    f"**Dependency Requirement:** The following work is still needed: {heuristic_result.missing_elements}. "
                    f"Route to one of: `{specialists_str}` to complete this work."
                )
                return {
                    "messages": [AIMessage(content=guidance_msg)],
                    "task_is_complete": False,
                    "artifacts": {
                        "exit_interview_result": {
                            "is_complete": False,
                            "reasoning": heuristic_result.reasoning,
                            "missing_elements": heuristic_result.missing_elements,
                            "recommended_specialists": recommended,
                            "method": "heuristic",
                            "return_control": heuristic_result.return_control.value
                        }
                    },
                    "scratchpad": {
                        "recommended_specialists": recommended,
                        "exit_interview_incomplete": True
                    }
                }

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

    def _evaluate_trace_heuristics(self, artifacts: dict) -> CompletionEvaluation | None:
        """
        ADR-CORE-058 Phase 1: Mechanical verification before LLM evaluation.

        Inspects research_trace artifacts for obvious failure signals that don't
        require LLM judgment to detect:
        - max_iterations_exceeded artifact present
        - Failed operations with no subsequent recovery

        Returns:
            CompletionEvaluation if obvious failure detected (early exit)
            None if no obvious failures (defer to LLM evaluation)
        """
        # Check for iteration limit hit (immediate INCOMPLETE)
        if artifacts.get("max_iterations_exceeded"):
            logger.info("ExitInterview heuristic: max_iterations_exceeded detected")
            return CompletionEvaluation(
                is_complete=False,
                reasoning="Task hit iteration limit before completion",
                missing_elements="Incomplete due to iteration limit - work was cut short",
                recommended_specialists=["project_director"]
            )

        # Find all research_trace artifacts
        traces = []
        for key, value in artifacts.items():
            if key.startswith("research_trace") and isinstance(value, list):
                traces.extend(value)

        if not traces:
            # No trace data, defer to LLM
            logger.debug("ExitInterview heuristic: no research_trace artifacts found")
            return None

        # Check for failed operations
        failed_ops = []
        last_failure_idx = -1
        for idx, entry in enumerate(traces):
            if isinstance(entry, dict) and not entry.get("success", True):
                failed_ops.append(entry)
                last_failure_idx = idx

        if failed_ops:
            # Check if there was successful recovery after the last failure
            successful_after = False
            if last_failure_idx < len(traces) - 1:
                for entry in traces[last_failure_idx + 1:]:
                    if isinstance(entry, dict) and entry.get("success", False):
                        successful_after = True
                        break

            if not successful_after:
                # Task ended with unrecovered failure
                last_failure = failed_ops[-1]
                tool_name = last_failure.get("tool", "unknown")
                error_msg = last_failure.get("error", "operation failed")
                logger.info(
                    f"ExitInterview heuristic: unrecovered failure detected - "
                    f"{tool_name}: {error_msg}"
                )
                return CompletionEvaluation(
                    is_complete=False,
                    reasoning=f"Task ended with failed operation: {tool_name}",
                    missing_elements=f"Failed: {error_msg}",
                    recommended_specialists=["project_director"]
                )

        # No obvious failures detected, defer to LLM evaluation
        logger.debug("ExitInterview heuristic: trace looks clean, deferring to LLM")
        return None

    def _evaluate_completion(
        self,
        user_request: str,
        recommended_specialists: list,
        routing_history: list,
        artifact_keys: list,
        recent_summary: str
    ) -> CompletionEvaluation:
        """
        Use LLM to evaluate if the task is complete.

        This is the core judgment: given what was requested and what has been done,
        can we provide a satisfying response to the user?
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

        # Format the prompt with current state
        prompt = prompt_template.format(
            user_request=user_request or "[Unable to extract original request]",
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
            # Truncate long content
            if len(content) > 200:
                content = content[:200] + "..."
            summaries.append(f"[{msg_type}]: {content}")
        return "\n".join(summaries)

    def _get_default_prompt(self) -> str:
        """Default prompt if exit_interview_prompt.md is not found."""
        return """You are evaluating whether a task is complete.

**Original User Request:**
{user_request}

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
2. If specialists were recommended, have the appropriate ones executed?
3. Are there meaningful artifacts or responses that answer the request?

Be CONSERVATIVE: If in doubt, mark as INCOMPLETE to give the system another chance.
The only cost of being conservative is one more routing cycle.
The cost of premature completion is an unsatisfied user.

Return your evaluation as JSON with:
- is_complete: boolean
- reasoning: brief explanation (1-2 sentences)
- missing_elements: what's still needed if incomplete (empty string if complete)
- recommended_specialists: list of specialist(s) that should handle the missing work (e.g., ["project_director"] for file operations)
"""
