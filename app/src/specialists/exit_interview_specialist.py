# app/src/specialists/exit_interview_specialist.py
"""
Exit Interview Specialist — verification gate before END (#195).

Gates the END node by verifying that accumulated state satisfies the user's
original request. Uses react_step tool loop to inspect the filesystem and
artifacts directly — no inference from summaries.

Flow:
    Router decides END → exit_interview_specialist → {complete → END, incomplete → Router}

Tools: list_directory, read_file (filesystem MCP), list_artifacts, retrieve_artifact
(shared artifact tools), DONE (structured evaluation signal).

Requires prompt-prix MCP for react_step. When unavailable, returns an honest
"cannot verify" signal rather than a degraded evaluation (#195).
"""

import json as _json
import logging
from typing import Dict, Any, List

from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..utils.cancellation_manager import CancellationManager
from ..mcp import (
    ToolDef, is_react_available, call_react_step, build_tool_schemas,
    dispatch_external_tool, artifact_tool_defs, dispatch_artifact_tool,
    ARTIFACT_TOOL_PARAMS, make_terminal_trace_entry,
)

logger = logging.getLogger(__name__)

# ─── Tool parameter schemas ─────────────────────────────────────────────────

_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
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
    **ARTIFACT_TOOL_PARAMS,
    # ADR-CORE-045: fork() for per-item verification
    "fork": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Verification task for the subagent. E.g., 'Verify that /workspace/reports/Q1.md exists and contains quarterly revenue data.'",
            },
            "context": {
                "type": "string",
                "description": "Optional context — file path or artifact key the subagent should inspect.",
            },
            "expected_artifacts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Artifact keys you need back. E.g., ['verification_result'] for a PASS/FAIL check.",
            },
        },
        "required": ["prompt"],
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


# ─── Evaluation schema ──────────────────────────────────────────────────────

class CompletionEvaluation(BaseModel):
    """Structured output from the DONE tool call."""
    is_complete: bool = Field(..., description="Whether the task is complete")
    reasoning: str = Field(..., description="Brief explanation of the evaluation")
    missing_elements: str = Field(
        default="",
        description="What's still needed if incomplete (empty if complete)"
    )
    recommended_specialists: List[str] = Field(
        default_factory=list,
        description="Which specialist(s) should handle the missing work"
    )


# ─── Specialist ─────────────────────────────────────────────────────────────

class ExitInterviewSpecialist(BaseSpecialist):
    """
    Verification gate before END.

    Runs a react_step tool loop to inspect the filesystem and artifacts,
    then calls DONE with a structured CompletionEvaluation.

    If complete:   task_is_complete=True  → END
    If incomplete:  task_is_complete=False → Facilitator → Router → specialist
    """

    DEFAULT_MAX_ITERATIONS = 8  # Read-only verification; shouldn't need many steps

    _routable_specialists: List[str] = []

    def set_routable_specialists(self, names: List[str]) -> None:
        """Inject routable specialist names (from graph_builder) for DONE schema enum."""
        self._routable_specialists = list(names)

    # ─── Main execution ──────────────────────────────────────────────────

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        artifacts = state.get("artifacts", {})
        user_request = artifacts.get("user_request", "")
        routing_history = state.get("routing_history", [])

        # #203: Read run_id for fork cancellation propagation
        run_id = state.get("run_id")
        # ADR-CORE-045: Read fork depth for recursion limit enforcement
        fork_depth = state.get("scratchpad", {}).get("fork_depth", 0)

        # Snapshot artifacts for local tool dispatch
        captured_artifacts = artifacts.copy()

        # Lazy exit_plan via SA MCP (#115, #129)
        exit_plan = self._ensure_exit_plan(artifacts, user_request)

        # Require react_step — no degraded evaluation (#195)
        if not is_react_available(getattr(self, 'external_mcp_client', None)):
            logger.warning("ExitInterviewSpecialist: prompt-prix unavailable — cannot verify")
            return self._build_unavailable_result(exit_plan)

        evaluation, trace = self._verify(
            user_request, exit_plan, routing_history, artifacts, captured_artifacts,
            run_id=run_id, fork_depth=fork_depth,
        )

        logger.info(
            f"ExitInterviewSpecialist: {'COMPLETE' if evaluation.is_complete else 'INCOMPLETE'} "
            f"— {evaluation.reasoning}"
        )

        if evaluation.is_complete:
            return self._build_complete_result(evaluation, exit_plan, trace)
        return self._build_incomplete_result(evaluation, exit_plan, trace)

    # ─── react_step verification loop ────────────────────────────────────

    def _verify(
        self,
        user_request: str,
        exit_plan: dict,
        routing_history: list,
        artifacts: dict,
        captured_artifacts: dict,
        run_id: str | None = None,
        fork_depth: int = 0,
    ) -> tuple[CompletionEvaluation, List[Dict[str, Any]]]:
        """Run the react_step verification loop. Returns (evaluation, trace)."""
        tools = self._build_tools()
        tool_params = self._build_tool_params()
        tool_schemas = build_tool_schemas(tools, tool_params)
        model_id = getattr(self.llm_adapter, 'model_name', "default") if self.llm_adapter else "default"
        system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
        task_prompt = self._build_task_prompt(user_request, exit_plan, routing_history, artifacts)

        max_iterations = self._get_max_iterations()
        trace: List[Dict[str, Any]] = []
        call_counter = 0

        for iteration in range(max_iterations):
            # #203: Check cancellation between react iterations
            if run_id and CancellationManager.is_cancelled(run_id):
                logger.warning(f"ExitInterviewSpecialist: run {run_id} cancelled at iteration {iteration}")
                cancel_msg = f"Run cancelled at iteration {iteration}"
                trace.append(make_terminal_trace_entry("CANCELLED", iteration, cancel_msg, False))
                return CompletionEvaluation(
                    is_complete=False,
                    reasoning=cancel_msg,
                ), trace

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
            evaluation = None

            # completed=True means prompt-prix v0.3.0 intercepted DONE
            if result.get("completed"):
                # #215: Record DONE in trace from prompt-prix done_trace_entry
                done_entry = result.get("done_trace_entry")
                if done_entry:
                    done_entry["iteration"] = iteration
                    done_entry["observation"] = _json.dumps(result.get("done_args", {}), default=str)
                    done_entry["success"] = True
                    trace.append(done_entry)
                evaluation = self._parse_completed_result(result)

            # Dispatch non-DONE pending tool calls
            for tc in result.get("pending_tool_calls", []):
                tool_name = tc.get("name", "")
                tool_args = tc.get("args", {})

                if tool_name == "DONE":
                    trace.append(make_terminal_trace_entry(
                        "DONE", iteration, _json.dumps(tool_args, default=str), True, tool_args,
                    ))
                    evaluation = self._parse_done_args(tool_args)
                    break

                observation = self._dispatch_tool(
                    tool_name, tool_args, tools, captured_artifacts,
                    run_id=run_id, fork_depth=fork_depth,
                )
                trace.append({
                    "iteration": iteration,
                    "tool_call": {"id": tc.get("id", ""), "name": tool_name, "args": tool_args},
                    "observation": observation,
                    "success": not observation.startswith("Error:"),
                })

            if not result.get("pending_tool_calls") and not result.get("completed"):
                logger.warning("ExitInterviewSpecialist: react_step returned no tool calls and not completed")
                trace.append(make_terminal_trace_entry(
                    "NO_TOOLS", iteration,
                    "react_step returned no tool calls and not completed", False,
                ))
                break

            # Tool-use-before-DONE guard (#193)
            if evaluation is not None:
                has_real_verification = any(
                    entry.get("tool_call", {}).get("name") not in ("SYSTEM", "DONE")
                    for entry in trace
                )
                if not has_real_verification:
                    logger.warning("ExitInterviewSpecialist: DONE before any real tool use — nudging")
                    trace.append({
                        "iteration": iteration,
                        "tool_call": {"id": "system", "name": "SYSTEM", "args": {}},
                        "observation": (
                            "You must call at least one verification tool "
                            "(list_directory, read_file, list_artifacts, retrieve_artifact) "
                            "before calling DONE. Verify real outcomes first."
                        ),
                        "success": False,
                    })
                    continue
                return evaluation, trace

        # Max iterations without DONE — honest "couldn't verify"
        logger.warning(
            f"ExitInterviewSpecialist: hit {max_iterations} iterations without DONE"
        )
        trace.append(make_terminal_trace_entry(
            "MAX_ITERATIONS", max_iterations - 1,
            f"Verification did not complete within {max_iterations} iterations", False,
            {"max_iterations": max_iterations},
        ))
        return CompletionEvaluation(
            is_complete=False,
            reasoning=f"Verification did not complete within {max_iterations} iterations — defaulting to incomplete",
            missing_elements="EI verification loop exhausted without reaching a conclusion",
        ), trace

    # ─── Tool definitions ────────────────────────────────────────────────

    def _build_tools(self) -> Dict[str, ToolDef]:
        """Build the tool routing table for verification."""
        tools = {
            # Filesystem (external MCP)
            "list_directory": ToolDef(
                service="filesystem", function="list_directory",
                description="List files and directories at a path.",
            ),
            "read_file": ToolDef(
                service="filesystem", function="read_file",
                description="Read file contents at a path.",
            ),
            # Artifact inspection (shared local tools)
            **artifact_tool_defs(),
            # ADR-CORE-045: fork() for per-item verification
            "fork": ToolDef(
                service="las", function="fork",
                description=(
                    "Spawn a subagent to verify a single item independently. "
                    "Use when verifying N items — fork once per item instead "
                    "of reading all files sequentially in this context."
                ),
                is_external=False,
            ),
            # Termination signal
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
        return tools

    def _build_tool_params(self) -> Dict[str, Dict[str, Any]]:
        """Build tool param schemas. Adds dynamic enum for recommended_specialists."""
        params = dict(_TOOL_PARAMS)
        if self._routable_specialists:
            done_schema = dict(params["DONE"])
            done_props = dict(done_schema["properties"])
            done_props["recommended_specialists"] = {
                "type": "array",
                "items": {"type": "string", "enum": self._routable_specialists},
                "description": "Which specialist(s) should handle missing work",
            }
            done_schema["properties"] = done_props
            params["DONE"] = done_schema
        return params

    def _get_max_iterations(self) -> int:
        """Get max iterations from specialist config."""
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _dispatch_tool(
        self, tool_name: str, tool_args: dict,
        tools: Dict[str, ToolDef], captured_artifacts: dict,
        run_id: str | None = None,
        fork_depth: int = 0,
    ) -> str:
        """Route a tool call to the appropriate handler."""
        tool_def = tools.get(tool_name)
        if not tool_def:
            return f"Error: Unknown tool '{tool_name}'"

        # ADR-CORE-045: fork() — recursive LAS invocation for per-item verification
        if tool_def.service == "las" and tool_def.function == "fork":
            from ..mcp.fork import dispatch_fork, extract_fork_result
            expected = tool_args.get("expected_artifacts")
            child_state = dispatch_fork(
                compiled_graph=self._compiled_graph,
                prompt=tool_args.get("prompt", ""),
                context=tool_args.get("context"),
                expected_artifacts=expected,
                parent_run_id=run_id,
                fork_depth=fork_depth,
            )
            return extract_fork_result(child_state, expected_artifacts=expected)

        # Local artifact tools
        if not tool_def.is_external:
            return dispatch_artifact_tool(tool_name, tool_args, captured_artifacts)

        # External filesystem tools
        return dispatch_external_tool(self.external_mcp_client, tool_def, tool_args)

    # ─── Prompt helpers ──────────────────────────────────────────────────

    def _build_task_prompt(
        self, user_request: str, exit_plan: dict,
        routing_history: list, artifacts: dict,
    ) -> str:
        """Build the task-specific prompt (Layer 2, like PD's _build_task_prompt)."""
        parts = [f"**Original User Request:**\n{user_request or '[Unknown]'}"]

        if exit_plan:
            parts.append(f"**Success Criteria:**\n{self._format_exit_plan(exit_plan)}")

        parts.append(
            f"**Specialists That Have Executed:**\n"
            f"{', '.join(routing_history[-10:]) if routing_history else '[None]'}"
        )

        artifact_keys = sorted(k for k in artifacts.keys() if not k.startswith("_"))
        parts.append(
            f"**Artifact Keys Available:**\n"
            f"{', '.join(artifact_keys) if artifact_keys else '[None]'}"
        )

        parts.append("Begin verification. Use tools to check real outcomes, then call DONE.")
        return "\n\n".join(parts)

    # ─── Exit plan helpers ───────────────────────────────────────────────

    def _ensure_exit_plan(self, artifacts: dict, user_request: str) -> dict:
        """Lazy-create exit_plan via SA MCP if needed (#115, #129)."""
        exit_plan = artifacts.get("exit_plan", {})
        if exit_plan:
            logger.info("ExitInterviewSpecialist: Using existing exit_plan")
            return exit_plan

        if not self.mcp_client:
            logger.info("ExitInterviewSpecialist: No MCP client — proceeding without exit_plan")
            return {}

        logger.info("ExitInterviewSpecialist: No exit_plan found, calling SA via MCP")

        task_plan = artifacts.get("task_plan", {})
        acceptance_criteria = task_plan.get("acceptance_criteria", "")
        criteria_section = (
            f"\n\nAcceptance criteria (what the completed work looks like):\n{acceptance_criteria}"
            if acceptance_criteria else ""
        )

        verification_context = (
            f"User request: {user_request}{criteria_section}\n\n"
            f"Generate a VERIFICATION PLAN with steps to CHECK that this work was completed correctly.\n"
            f"These are steps to VERIFY completion, NOT steps to implement the task."
        )

        # Pass EI's tool inventory so SA constrains steps accordingly
        verification_tools = [
            {"name": name, "description": tool_def.description}
            for name, tool_def in self._build_tools().items()
            if name != "DONE"
        ]

        try:
            result = self.mcp_client.call(
                "systems_architect", "create_plan",
                context=verification_context,
                artifact_key="exit_plan",
                available_tools=verification_tools,
            )
            exit_plan = result.get("artifacts", {}).get("exit_plan", {})
            logger.info(f"ExitInterviewSpecialist: SA produced exit_plan: {exit_plan.get('plan_summary', '?')}")
            return exit_plan
        except Exception as e:
            logger.warning(f"ExitInterviewSpecialist: SA MCP call failed: {e}")
            return {}

    def _format_exit_plan(self, exit_plan: dict) -> str:
        """Format the exit_plan artifact for prompts. No truncation (#183)."""
        parts = []
        if "plan_summary" in exit_plan:
            parts.append(f"**Plan Summary:** {exit_plan['plan_summary']}")
        if "success_criteria" in exit_plan:
            parts.append(f"**Success Criteria:** {exit_plan['success_criteria']}")
        if "execution_steps" in exit_plan:
            steps = exit_plan["execution_steps"]
            if isinstance(steps, list):
                steps_str = "\n".join(f"  - {s}" for s in steps)
                parts.append(f"**Verification Steps:**\n{steps_str}")
        if "steps" in exit_plan:
            steps = exit_plan["steps"]
            if isinstance(steps, list):
                steps_str = "\n".join(f"  - {s}" for s in steps)
                parts.append(f"**Planned Steps:**\n{steps_str}")
        if "expected_artifacts" in exit_plan:
            parts.append(f"**Expected Artifacts:** {exit_plan['expected_artifacts']}")
        if not parts:
            try:
                parts.append(f"**Full Plan:**\n{_json.dumps(exit_plan, indent=2, default=str)}")
            except (TypeError, ValueError):
                parts.append(f"**Full Plan:** {str(exit_plan)}")
        return "\n\n".join(parts)

    # ─── Result parsing ──────────────────────────────────────────────────

    def _parse_done_args(self, args: dict) -> CompletionEvaluation:
        """Parse DONE tool call args into CompletionEvaluation."""
        return CompletionEvaluation(
            is_complete=args.get("is_complete", False),
            reasoning=args.get("reasoning", "Verification complete"),
            missing_elements=args.get("missing_elements", ""),
            recommended_specialists=args.get("recommended_specialists", []),
        )

    def _parse_completed_result(self, result: dict) -> CompletionEvaluation:
        """Parse a completed react_step result (DONE intercepted by prompt-prix v0.3.0)."""
        done_args = result.get("done_args")
        if done_args and "is_complete" in done_args:
            return self._parse_done_args(done_args)

        final_response = result.get("final_response", "")
        if not final_response:
            return CompletionEvaluation(
                is_complete=False,
                reasoning="Verification produced no final response — defaulting to incomplete",
                missing_elements="EI verification returned empty result",
            )

        # Model may return DONE-like JSON as final text
        try:
            data = _json.loads(final_response) if isinstance(final_response, str) else final_response
            if isinstance(data, dict) and "is_complete" in data:
                return CompletionEvaluation(**data)
        except (ValueError, TypeError):
            pass

        logger.warning(f"ExitInterviewSpecialist: Could not parse verification result")
        return CompletionEvaluation(
            is_complete=False,
            reasoning="Could not parse verification result — defaulting to incomplete",
            missing_elements="EI verification produced unparseable response",
        )

    # ─── Result builders ─────────────────────────────────────────────────

    def _build_complete_result(
        self, evaluation: CompletionEvaluation, exit_plan: dict,
        trace: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        result = {
            "messages": [AIMessage(
                content=f"[Exit Interview] Task verified complete: {evaluation.reasoning}"
            )],
            "task_is_complete": True,
            "artifacts": {
                "exit_plan": exit_plan,
                "exit_interview_result": {
                    "is_complete": True,
                    "reasoning": evaluation.reasoning,
                },
            },
        }
        if trace:
            result["scratchpad"] = {"react_trace": trace}
        return result

    def _build_incomplete_result(
        self, evaluation: CompletionEvaluation, exit_plan: dict,
        trace: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        recommended = evaluation.recommended_specialists or ["project_director"]
        specialists_str = ", ".join(recommended)
        scratchpad: Dict[str, Any] = {
            "recommended_specialists": recommended,
            "exit_interview_incomplete": True,
        }
        if trace:
            scratchpad["react_trace"] = trace
        return {
            "messages": [AIMessage(content=(
                f"[Exit Interview] Task not complete: {evaluation.reasoning}\n\n"
                f"**Dependency Requirement:** The following work is still needed: "
                f"{evaluation.missing_elements}. "
                f"Route to one of: `{specialists_str}` to complete this work."
            ))],
            "task_is_complete": False,
            "artifacts": {
                "exit_plan": exit_plan,
                "exit_interview_result": {
                    "is_complete": False,
                    "reasoning": evaluation.reasoning,
                    "missing_elements": evaluation.missing_elements,
                    "recommended_specialists": recommended,
                },
            },
            "scratchpad": scratchpad,
        }

    def _build_unavailable_result(self, exit_plan: dict) -> Dict[str, Any]:
        """Honest signal when prompt-prix is unavailable (#195)."""
        return {
            "messages": [AIMessage(
                content=(
                    "[Exit Interview] Cannot verify task completion — "
                    "prompt-prix MCP unavailable. Defaulting to complete."
                )
            )],
            "task_is_complete": True,
            "artifacts": {
                "exit_plan": exit_plan,
                "exit_interview_result": {
                    "is_complete": True,
                    "reasoning": "prompt-prix unavailable — cannot verify, defaulting to complete",
                },
            },
        }
