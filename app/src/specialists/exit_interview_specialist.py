# app/src/specialists/exit_interview_specialist.py
"""
Exit Interview Specialist - ADR-ROADMAP-001 Phase 1 + #173 react_step verification

Gates the END node by validating that the accumulated state actually satisfies
the user's original request. This prevents premature termination when Router
decides to end but the task isn't truly complete.

Flow:
    Router decides END → exit_interview_specialist → {complete → END, incomplete → Router}

#173: When react_step is available (prompt-prix connected), EI verifies outcomes
by directly inspecting the filesystem and artifacts via tool calls. Falls back
to single-pass LLM evaluation when react_step is unavailable.
"""

import json as _json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from .schemas import ReturnControlMode
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt
from ..mcp import (
    ToolDef, is_react_available, call_react_step, build_tool_schemas,
    dispatch_external_tool,
)

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


# ─── Local artifact tools (#174) ──────────────────────────────────────────────

def _list_artifacts_tool(captured_artifacts: dict) -> str:
    """Local tool: list available artifact keys with type/size hints."""
    if not captured_artifacts:
        return "No artifacts available."
    lines = []
    for key in sorted(captured_artifacts.keys()):
        value = captured_artifacts[key]
        if isinstance(value, dict):
            lines.append(f"  {key}: dict ({len(value)} keys)")
        elif isinstance(value, list):
            lines.append(f"  {key}: list ({len(value)} items)")
        elif isinstance(value, str):
            lines.append(f"  {key}: str ({len(value)} chars)")
        elif isinstance(value, bytes):
            lines.append(f"  {key}: bytes ({len(value)} bytes)")
        else:
            lines.append(f"  {key}: {type(value).__name__}")
    return "Artifacts:\n" + "\n".join(lines)


def _browse_artifact_tool(captured_artifacts: dict, key: str) -> str:
    """Local tool: browse a specific artifact's content."""
    if key not in captured_artifacts:
        return f"Error: Artifact '{key}' not found. Use list_artifacts to see available keys."
    value = captured_artifacts[key]
    return ExitInterviewSpecialist._preview_artifact_value(value, max_len=2000)


# ─── Tool parameter schemas ───────────────────────────────────────────────────

_EI_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
    "list_directory": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Directory path to list"}},
        "required": ["path"],
    },
    "read_file": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "File path to read"}},
        "required": ["path"],
    },
    "list_artifacts": {
        "type": "object",
        "properties": {},
    },
    "browse_artifact": {
        "type": "object",
        "properties": {"key": {"type": "string", "description": "Artifact key to browse"}},
        "required": ["key"],
    },
    "DONE": {
        "type": "object",
        "properties": {
            "is_complete": {"type": "boolean", "description": "Whether the task is verified complete"},
            "reasoning": {"type": "string", "description": "Brief explanation (1-2 sentences)"},
            "missing_elements": {"type": "string", "description": "What's still needed if incomplete (empty if complete)"},
            "recommended_specialists": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Which specialist(s) should handle missing work",
            },
        },
        "required": ["is_complete", "reasoning"],
    },
}


class ExitInterviewSpecialist(BaseSpecialist):
    """
    Validates task completion before allowing workflow to terminate.

    This specialist acts as a gate before END, evaluating whether the accumulated
    state (artifacts, messages, context_plan) satisfies the original user request.

    If complete: Sets task_is_complete=True, allowing standard edge to route to END
    If incomplete: Does NOT set task_is_complete, causing route back to Router

    #173: When react_step is available, EI verifies outcomes by calling filesystem
    and artifact tools directly instead of inferring from trace data.
    """

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Evaluate if the task is semantically complete.

        #173: Two-mode evaluation:
        1. react_step mode: Verify outcomes via tool calls (filesystem, artifacts)
        2. Fallback mode: Single-pass LLM evaluation from artifact summaries
        """
        artifacts = state.get("artifacts", {})
        messages = state.get("messages", [])

        # Capture artifacts for local tool dispatch (#174)
        self._captured_artifacts = artifacts.copy()

        # Get original user request
        user_request = artifacts.get("user_request", "")
        if not user_request and messages:
            for msg in messages:
                if hasattr(msg, 'type') and msg.type == 'human':
                    user_request = msg.content
                    break
                elif hasattr(msg, 'content') and not hasattr(msg, 'type'):
                    user_request = msg.content
                    break

        # Get context_plan if available (Triage's assessment)
        context_plan = artifacts.get("context_plan", {})
        recommended_specialists = context_plan.get("recommended_specialists", [])

        # Get routing history to see what has executed
        routing_history = state.get("routing_history", [])

        # Issue #115: Lazy initialization of exit_plan via SA MCP tool
        # Issue #129: Request a VERIFICATION plan, not an implementation plan
        exit_plan = artifacts.get("exit_plan", {})
        if not exit_plan and self.mcp_client:
            logger.info("ExitInterviewSpecialist: No exit_plan found, calling SA via MCP")
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
                exit_plan = {}
        elif exit_plan:
            logger.info(f"ExitInterviewSpecialist: Using existing exit_plan for verification")

        # #173: Choose evaluation mode based on react_step availability
        if self._has_react_capability():
            logger.info("ExitInterviewSpecialist: Using react_step verification mode")
            evaluation = self._evaluate_via_react_step(
                user_request, exit_plan, routing_history, artifacts, messages
            )
        else:
            logger.info("ExitInterviewSpecialist: Using single-pass LLM fallback")
            artifact_summary = self._build_artifact_summary(artifacts)
            recent_messages = messages[-5:] if len(messages) > 5 else messages
            recent_summary = self._summarize_messages(recent_messages)
            evaluation = self._evaluate_completion(
                user_request=user_request,
                exit_plan=exit_plan,
                recommended_specialists=recommended_specialists,
                routing_history=routing_history,
                artifact_summary=artifact_summary,
                recent_summary=recent_summary
            )

        logger.info(
            f"ExitInterviewSpecialist: {'COMPLETE' if evaluation.is_complete else 'INCOMPLETE'} "
            f"- {evaluation.reasoning}"
        )

        # Build return dict (same for both modes)
        if evaluation.is_complete:
            return {
                "messages": [AIMessage(content=f"[Exit Interview] Task verified complete: {evaluation.reasoning}")],
                "task_is_complete": True,
                "artifacts": {
                    "exit_plan": exit_plan,
                    "exit_interview_result": {
                        "is_complete": True,
                        "reasoning": evaluation.reasoning
                    }
                }
            }
        else:
            recommended = evaluation.recommended_specialists or ["project_director"]
            specialists_str = ", ".join(recommended)
            guidance_msg = (
                f"[Exit Interview] Task not complete: {evaluation.reasoning}\n\n"
                f"**Dependency Requirement:** The following work is still needed: {evaluation.missing_elements}. "
                f"Route to one of: `{specialists_str}` to complete this work."
            )
            return {
                "messages": [AIMessage(content=guidance_msg)],
                "task_is_complete": False,
                "artifacts": {
                    "exit_plan": exit_plan,
                    "exit_interview_result": {
                        "is_complete": False,
                        "reasoning": evaluation.reasoning,
                        "missing_elements": evaluation.missing_elements,
                        "recommended_specialists": recommended,
                        "return_control": evaluation.return_control
                    }
                },
                "scratchpad": {
                    "recommended_specialists": recommended,
                    "exit_interview_incomplete": True
                }
            }

    # ─── react_step verification (#173) ────────────────────────────────────────

    def _has_react_capability(self) -> bool:
        """Check if prompt-prix MCP is available for react_step verification."""
        return (
            hasattr(self, 'external_mcp_client')
            and self.external_mcp_client is not None
            and hasattr(self.external_mcp_client, 'is_connected')
            and self.external_mcp_client.is_connected("prompt-prix")
        )

    def _evaluate_via_react_step(
        self,
        user_request: str,
        exit_plan: dict,
        routing_history: list,
        artifacts: dict,
        messages: list,
    ) -> CompletionEvaluation:
        """
        #173: Verify task completion via react_step tool loop.

        The model can call filesystem tools (list_directory, read_file) to check
        real outcomes, and artifact tools (list_artifacts, browse_artifact) to
        inspect workflow state. When satisfied, it calls DONE with its evaluation.
        """
        tools = self._build_verification_tools()
        tool_schemas = build_tool_schemas(tools, _EI_TOOL_PARAMS)
        model_id = getattr(self.llm_adapter, 'model_name', "default") if self.llm_adapter else "default"

        system_prompt = self._build_verification_system_prompt()
        task_prompt = self._build_verification_task_prompt(
            user_request, exit_plan, routing_history, artifacts
        )

        trace = []
        call_counter = 0
        max_iterations = 8  # Read-only verification, shouldn't need many steps

        for iteration in range(max_iterations):
            result = call_react_step(
                self.external_mcp_client,
                model_id=model_id,
                system_prompt=system_prompt,
                task_prompt=task_prompt,
                trace=trace,
                tool_schemas=tool_schemas,
                call_counter=call_counter,
                timeout=120.0,
            )

            call_counter = result.get("call_counter", call_counter + 1)

            if result.get("completed"):
                return self._parse_verification_result(result)

            pending = result.get("pending_tool_calls", [])
            if not pending:
                logger.warning("ExitInterviewSpecialist: react_step returned no tool calls and not completed")
                break

            for tc in pending:
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})

                # Check for DONE tool — immediate return
                if tool_name == "DONE":
                    return self._parse_done_tool(tool_args)

                observation = self._dispatch_verification_tool(tool_name, tool_args, tools)
                trace.append({
                    "iteration": iteration,
                    "tool_call": {"id": tc.get("id", ""), "name": tool_name, "args": tool_args},
                    "observation": observation,
                    "success": not observation.startswith("Error:"),
                })

        # Max iterations without DONE — fall back to single-pass
        logger.warning(
            f"ExitInterviewSpecialist: react_step verification hit {max_iterations} iterations, "
            f"falling back to single-pass LLM"
        )
        artifact_summary = self._build_artifact_summary(artifacts)
        recent_summary = self._summarize_messages(messages[-5:] if len(messages) > 5 else messages)
        return self._evaluate_completion(
            user_request=user_request,
            exit_plan=exit_plan,
            recommended_specialists=[],
            routing_history=routing_history,
            artifact_summary=artifact_summary,
            recent_summary=recent_summary,
        )

    def _build_verification_tools(self) -> Dict[str, ToolDef]:
        """Build the tool routing table for verification."""
        return {
            "list_directory": ToolDef(
                service="filesystem", function="list_directory",
                description="List files and directories at a path.",
            ),
            "read_file": ToolDef(
                service="filesystem", function="read_file",
                description="Read file contents at a path.",
            ),
            "list_artifacts": ToolDef(
                service="local", function="list_artifacts",
                description="List all artifacts in the workflow state with type hints.",
                is_external=False,
            ),
            "browse_artifact": ToolDef(
                service="local", function="browse_artifact",
                description="Browse a specific artifact's content by key.",
                is_external=False,
            ),
            "DONE": ToolDef(
                service="local", function="DONE",
                description=(
                    "Signal verification complete. Args: is_complete (bool), "
                    "reasoning (str), missing_elements (str, optional), "
                    "recommended_specialists (list[str], optional)."
                ),
                is_external=False,
            ),
        }

    def _dispatch_verification_tool(
        self, tool_name: str, tool_args: dict, tools: Dict[str, ToolDef]
    ) -> str:
        """Route a verification tool call to the appropriate handler."""
        tool_def = tools.get(tool_name)
        if not tool_def:
            return f"Error: Unknown tool '{tool_name}'"

        # Local dispatch for artifact tools
        if not tool_def.is_external:
            if tool_name == "list_artifacts":
                return _list_artifacts_tool(self._captured_artifacts)
            elif tool_name == "browse_artifact":
                return _browse_artifact_tool(self._captured_artifacts, tool_args.get("key", ""))
            return f"Error: Unknown local tool '{tool_name}'"

        # External dispatch for filesystem tools
        return dispatch_external_tool(self.external_mcp_client, tool_def, tool_args)

    def _build_verification_system_prompt(self) -> str:
        """System prompt for react_step verification mode."""
        return """You are a verification evaluator for an agentic workflow system.

Your job is to VERIFY whether the workflow actually completed the user's task by inspecting real outcomes — not by reading claims in messages or trace data.

## Available Tools

- **list_directory(path)** — List files in a directory to verify file operations
- **read_file(path)** — Read file contents to verify content correctness
- **list_artifacts()** — List all artifacts in the workflow state
- **browse_artifact(key)** — Read the content of a specific artifact
- **DONE(is_complete, reasoning, missing_elements, recommended_specialists)** — Signal your verification is complete

## Verification Process

1. Review the user request and success criteria below
2. Use tools to verify outcomes:
   - For file operations: list directories, read files to check content
   - For analysis tasks: browse artifacts to check results
   - For research tasks: browse artifacts to check gathered information
3. Call DONE with your evaluation when verification is complete

## Rules

- VERIFY, don't trust. Check the actual filesystem state for file operations.
- Be efficient. You typically need 2-4 tool calls to verify.
- Call DONE as soon as you have enough evidence to decide.
- Default to project_director in recommended_specialists for file operation gaps."""

    def _build_verification_task_prompt(
        self,
        user_request: str,
        exit_plan: dict,
        routing_history: list,
        artifacts: dict,
    ) -> str:
        """Build the task prompt with context for verification."""
        parts = [f"**Original User Request:**\n{user_request or '[Unknown]'}"]

        if exit_plan:
            parts.append(f"**Success Criteria:**\n{self._format_exit_plan(exit_plan)}")

        parts.append(
            f"**Specialists That Have Executed:**\n"
            f"{', '.join(routing_history[-10:]) if routing_history else '[None]'}"
        )

        # Provide artifact keys so model knows what's available
        artifact_keys = sorted(k for k in artifacts.keys() if not k.startswith("_"))
        parts.append(f"**Artifact Keys Available:**\n{', '.join(artifact_keys) if artifact_keys else '[None]'}")

        parts.append("Begin verification. Use tools to check real outcomes, then call DONE.")
        return "\n\n".join(parts)

    def _parse_done_tool(self, args: dict) -> CompletionEvaluation:
        """Parse DONE tool call args into CompletionEvaluation."""
        return CompletionEvaluation(
            is_complete=args.get("is_complete", False),
            reasoning=args.get("reasoning", "Verification complete"),
            missing_elements=args.get("missing_elements", ""),
            recommended_specialists=args.get("recommended_specialists", []),
        )

    def _parse_verification_result(self, result: dict) -> CompletionEvaluation:
        """Parse a completed react_step result into CompletionEvaluation."""
        final_response = result.get("final_response", "")
        if not final_response:
            return CompletionEvaluation(
                is_complete=False,
                reasoning="Verification produced no final response — defaulting to incomplete",
                missing_elements="EI verification returned empty result",
            )

        # Try to parse as JSON (model may return DONE-like JSON as final text)
        try:
            data = _json.loads(final_response) if isinstance(final_response, str) else final_response
            if isinstance(data, dict) and "is_complete" in data:
                return CompletionEvaluation(**data)
        except (ValueError, TypeError):
            pass

        # Couldn't parse — default to incomplete
        logger.warning(f"ExitInterviewSpecialist: Could not parse verification result: {final_response[:200]}")
        return CompletionEvaluation(
            is_complete=False,
            reasoning="Could not parse verification result — defaulting to incomplete",
            missing_elements="EI verification produced unparseable response",
        )

    # ─── Single-pass LLM fallback ─────────────────────────────────────────────

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
        Fallback: single-pass LLM evaluation when react_step is unavailable.

        This is the original EI evaluation path — reads artifact summaries
        injected into the prompt and makes a judgment call.
        """
        if not self.llm_adapter:
            logger.warning("ExitInterviewSpecialist: No LLM adapter, defaulting to complete")
            return CompletionEvaluation(
                is_complete=True,
                reasoning="No LLM adapter available for evaluation - defaulting to complete",
                missing_elements=""
            )

        try:
            prompt_template = load_prompt("exit_interview_prompt.md")
        except (FileNotFoundError, IOError):
            prompt_template = self._get_default_prompt()

        if exit_plan:
            exit_plan_summary = self._format_exit_plan(exit_plan)
        else:
            exit_plan_summary = "[No exit plan available - verify based on user request only]"

        prompt = prompt_template.format(
            user_request=user_request or "[Unable to extract original request]",
            exit_plan=exit_plan_summary,
            recommended_specialists=", ".join(recommended_specialists) if recommended_specialists else "[No specific recommendations]",
            routing_history=", ".join(routing_history[-10:]) if routing_history else "[No routing history]",
            artifact_summary=artifact_summary or "[No artifacts produced]",
            recent_summary=recent_summary or "[No recent activity]"
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)]
        )

        try:
            response = self.llm_adapter.invoke(request)
            json_data = response.get("json_response")
            if json_data:
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

            text_response = response.get("text_response", "")
            logger.warning(f"ExitInterviewSpecialist: No JSON in response: {text_response[:200]}")
            return CompletionEvaluation(
                is_complete=False,
                reasoning="Could not parse LLM response - defaulting to incomplete (circuit breaker handles loop prevention)",
                missing_elements="EI could not evaluate — model produced no parseable JSON"
            )
        except Exception as e:
            logger.error(f"ExitInterviewSpecialist: LLM evaluation failed: {e}")
            return CompletionEvaluation(
                is_complete=True,
                reasoning=f"Evaluation error ({e}) - defaulting to complete to avoid loops",
                missing_elements=""
            )

    # ─── Shared helpers ────────────────────────────────────────────────────────

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

        Used by the single-pass LLM fallback path. The react_step path uses
        list_artifacts/browse_artifact tools instead.
        """
        excluded = {"gathered_context", "context_plan"}
        lines = []

        for key, value in artifacts.items():
            if key.startswith("_") or key in excluded:
                continue

            # Special handling: resume_trace gets an operation inventory
            if key == "resume_trace" and isinstance(value, list):
                preview = self._build_trace_summary(value)
            else:
                preview = self._preview_artifact_value(value, max_preview)
            lines.append(f"- **{key}**: {preview}")

        return "\n".join(lines) if lines else "[No artifacts produced]"

    @staticmethod
    def _preview_artifact_value(value, max_len: int = 300) -> str:
        """Produce a truncated text preview of an artifact value."""
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
        text = str(value)
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    @staticmethod
    def _build_trace_summary(trace: list) -> str:
        """
        Summarize resume_trace as an operation inventory for completion evaluation.

        Used by the single-pass LLM fallback. The react_step path can call
        browse_artifact("resume_trace") if needed.
        """
        if not trace:
            return "(empty trace)"

        tool_stats: dict = {}
        for entry in trace:
            if not isinstance(entry, dict):
                continue
            tc = entry.get("tool_call", {})
            name = tc.get("name") or entry.get("tool", "unknown")
            success = entry.get("success", True)

            if name not in tool_stats:
                tool_stats[name] = {"ok": 0, "fail": 0}
            if success:
                tool_stats[name]["ok"] += 1
            else:
                tool_stats[name]["fail"] += 1

        total = len(trace)
        lines = [f"(trace, {total} operations)"]
        for tool, stats in tool_stats.items():
            ok, fail = stats["ok"], stats["fail"]
            status = f"{ok} ok" + (f", {fail} fail" if fail else "")
            lines.append(f"  {tool}: {status}")

        recent = trace[-min(5, total):]
        lines.append("  Recent:")
        for entry in recent:
            tc = entry.get("tool_call", {})
            name = tc.get("name") or entry.get("tool", "?")
            args = tc.get("args") or entry.get("args", {})
            ok_str = "ok" if entry.get("success", True) else "FAIL"
            arg_preview = ", ".join(
                f"{k}={v}" for k, v in list(args.items())[:2]
            )
            lines.append(f"    [{ok_str}] {name}({arg_preview})")

        return "\n".join(lines)

    def _format_exit_plan(self, exit_plan: dict) -> str:
        """Format the exit_plan artifact for prompts."""
        parts = []
        if "plan_summary" in exit_plan:
            parts.append(f"**Plan Summary:** {exit_plan['plan_summary']}")
        if "success_criteria" in exit_plan:
            parts.append(f"**Success Criteria:** {exit_plan['success_criteria']}")
        if "execution_steps" in exit_plan:
            steps = exit_plan["execution_steps"]
            if isinstance(steps, list):
                steps_str = "\n".join(f"  - {s}" for s in steps[:10])
                parts.append(f"**Verification Steps:**\n{steps_str}")
        if "steps" in exit_plan:
            steps = exit_plan["steps"]
            if isinstance(steps, list):
                steps_str = "\n".join(f"  - {s}" for s in steps[:10])
                parts.append(f"**Planned Steps:**\n{steps_str}")
        if "expected_artifacts" in exit_plan:
            parts.append(f"**Expected Artifacts:** {exit_plan['expected_artifacts']}")
        if not parts:
            try:
                parts.append(f"**Full Plan:**\n{_json.dumps(exit_plan, indent=2, default=str)[:2000]}")
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

**IMPORTANT:** Do NOT trust claims of completed work in messages alone. For file operations, check the artifacts for concrete evidence — the `resume_trace` shows an operation inventory with tool counts and success/fail status. Operations may use dedicated tools (move_file, create_directory) OR shell commands via run_command (mv, mkdir -p). Both are equally valid. Count completed vs. expected operations.

Be CONSERVATIVE: If in doubt, mark as INCOMPLETE to give the system another chance.
The only cost of being conservative is one more routing cycle.
The cost of premature completion is an unsatisfied user.

Return your evaluation as JSON with:
- is_complete: boolean
- reasoning: brief explanation (1-2 sentences)
- missing_elements: what's still needed if incomplete (empty string if complete)
- recommended_specialists: list of specialist(s) that should handle the missing work (e.g., ["project_director"] for file operations)
"""
