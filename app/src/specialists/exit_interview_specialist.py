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
    return_control: str = Field(
        default="accumulate",
        description="How Facilitator handles retry: 'accumulate', 'reset', or 'delta'"
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
        # Issue #129: Request a VERIFICATION plan, not an implementation plan
        exit_plan = artifacts.get("exit_plan", {})
        if not exit_plan and self.mcp_client:
            logger.info("ExitInterviewSpecialist: No exit_plan found, calling SA via MCP")
            # Build verification-focused context for SA
            verification_context = f"""User request: {user_request}

Generate a VERIFICATION PLAN with steps to CHECK that this work was completed correctly.
Each step should be a verification action (list directory, count files, check file contents, verify artifact exists).
These are steps to VERIFY completion, NOT steps to implement the task.

Example verification steps:
- "List source directory to confirm it is empty (all files moved)"
- "Count files in each category folder"
- "Verify total file count matches expected count"
- "Check that artifact X exists in state"
"""
            try:
                result = self.mcp_client.call(
                    "systems_architect",
                    "create_plan",
                    context=verification_context,
                    artifact_key="exit_plan"
                )
                exit_plan = result.get("artifacts", {}).get("exit_plan", {})
                logger.info(f"ExitInterviewSpecialist: SA produced exit_plan: {exit_plan.get('plan_summary', '?')}")
            except Exception as e:
                logger.warning(f"ExitInterviewSpecialist: SA MCP call failed: {e}")
                exit_plan = {}  # Proceed without - EI handles missing gracefully
        elif exit_plan:
            logger.info(f"ExitInterviewSpecialist: Using existing exit_plan for verification")

        # Build artifact summary with value previews (#155)
        artifact_summary = self._build_artifact_summary(artifacts)

        # Get recent messages (last 5) for context
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        recent_summary = self._summarize_messages(recent_messages)

        logger.info(
            f"ExitInterviewSpecialist evaluating completion: "
            f"artifact_count={len(artifact_summary.splitlines())}, routing_history={routing_history[-3:]}"
        )

        # Evaluate completion using LLM
        evaluation = self._evaluate_completion(
            user_request=user_request,
            exit_plan=exit_plan,
            recommended_specialists=recommended_specialists,
            routing_history=routing_history,
            artifact_summary=artifact_summary,
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
                    # Issue #114: Don't clear max_iterations_exceeded - Facilitator consumes it
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
                    # Issue #114: Don't clear max_iterations_exceeded - Facilitator consumes it
                    "exit_interview_result": {
                        "is_complete": False,
                        "reasoning": evaluation.reasoning,
                        "missing_elements": evaluation.missing_elements,
                        "recommended_specialists": recommended,
                        "return_control": evaluation.return_control
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
        artifact_summary: str,
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
            artifact_summary=artifact_summary or "[No artifacts produced]",
            recent_summary=recent_summary or "[No recent activity]"
        )

        # Don't use output_model_class - not all models support structured output.
        # Instead, ask for JSON in the prompt and parse from text response.
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)]
        )

        try:
            response = self.llm_adapter.invoke(request)

            # Adapter handles JSON parsing - check json_response first
            json_data = response.get("json_response")
            if json_data:
                # Guard: LLM sometimes returns stray JSON (e.g. tool args from prior
                # specialist) instead of CompletionEvaluation. Check for the required
                # field before attempting construction to avoid noisy pydantic errors.
                if "is_complete" not in json_data:
                    logger.warning(
                        f"ExitInterviewSpecialist: JSON response missing 'is_complete' "
                        f"(got keys: {list(json_data.keys())}), defaulting to incomplete"
                    )
                    return CompletionEvaluation(
                        is_complete=False,
                        reasoning="LLM returned unrelated JSON - defaulting to incomplete (circuit breaker handles loop prevention)",
                        missing_elements="EI could not evaluate — model produced wrong JSON schema"
                    )
                return CompletionEvaluation(**json_data)

            # If no JSON found, default to incomplete — circuit breaker handles loop prevention
            text_response = response.get("text_response", "")
            logger.warning(f"ExitInterviewSpecialist: No JSON in response: {text_response[:200]}")
            return CompletionEvaluation(
                is_complete=False,
                reasoning="Could not parse LLM response - defaulting to incomplete (circuit breaker handles loop prevention)",
                missing_elements="EI could not evaluate — model produced no parseable JSON"
            )
        except Exception as e:
            # Graceful degradation: default to COMPLETE to avoid infinite loops
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

    def _build_artifact_summary(self, artifacts: dict, max_preview: int = 300) -> str:
        """
        Build artifact summary with value previews for completion evaluation (#155).

        Instead of just listing key names, includes truncated previews so EI can
        distinguish a successful analysis from an empty/error result.

        Excludes internal artifacts (prefixed with _) and large context artifacts
        (gathered_context, context_plan) that are already represented elsewhere.
        """
        import json as _json

        excluded = {"gathered_context", "context_plan"}
        lines = []

        for key, value in artifacts.items():
            if key.startswith("_") or key in excluded:
                continue

            preview = self._preview_artifact_value(value, max_preview)
            lines.append(f"- **{key}**: {preview}")

        return "\n".join(lines) if lines else "[No artifacts produced]"

    @staticmethod
    def _preview_artifact_value(value, max_len: int = 300) -> str:
        """Produce a truncated text preview of an artifact value."""
        import json as _json

        if value is None:
            return "(empty)"
        if isinstance(value, bytes):
            return f"(binary, {len(value)} bytes)"
        if isinstance(value, str):
            if len(value) <= max_len:
                return value
            return value[:max_len] + "..."
        if isinstance(value, dict):
            try:
                text = _json.dumps(value, default=str)
                if len(text) <= max_len:
                    return text
                return text[:max_len] + "..."
            except (TypeError, ValueError):
                return str(value)[:max_len] + "..."
        if isinstance(value, list):
            text = f"(list, {len(value)} items)"
            if value:
                first = str(value[0])
                if len(first) > 80:
                    first = first[:80] + "..."
                text += f" first: {first}"
            return text
        # Fallback for other types
        text = str(value)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

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

**Current Artifacts (with value previews):**
{artifact_summary}

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
