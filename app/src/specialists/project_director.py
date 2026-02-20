# app/src/specialists/project_director.py
"""
Project Director — autonomous agent for multi-step projects.

Uses prompt-prix MCP react_step() for iterative tool use (#162):
- Calls react_step() to get model's next tool calls
- Dispatches tool calls to real MCP services (filesystem, terminal, web)
- Feeds observations back to the trace
- Loops until completed or max_iterations

Replaces the former ReActMixin + ReactEnabledSpecialist pattern.
"""
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..utils.cancellation_manager import CancellationManager
from ..mcp import (
    ToolDef, is_react_available, call_react_step, build_tool_schemas,
    dispatch_external_tool, artifact_tool_defs, dispatch_artifact_tool,
    ARTIFACT_TOOL_PARAMS,
)
from ..resilience.cycle_detection import detect_cycle_with_pattern

logger = logging.getLogger(__name__)


# Tool parameter schemas for OpenAI function calling format
_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
    "search": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query string"}},
        "required": ["query"],
    },
    "browse": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "URL to fetch and parse"}},
        "required": ["url"],
    },
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
    "create_directory": {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Directory path to create"}},
        "required": ["path"],
    },
    "move_file": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source file path"},
            "destination": {"type": "string", "description": "Destination file path"},
        },
        "required": ["source", "destination"],
    },
    "write_file": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write to file"},
        },
        "required": ["path", "content"],
    },
    "run_command": {
        "type": "object",
        "properties": {"command": {"type": "string", "description": "Shell command to execute"}},
        "required": ["command"],
    },
    "fork": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Task prompt for the subagent. Write it like a task for a skilled colleague — say what you need, not how to do it.",
            },
            "context": {
                "type": "string",
                "description": "Optional context to pass (e.g., document content). Only what the subagent needs for this specific subtask.",
            },
        },
        "required": ["prompt"],
    },
}


# ─── Filesystem enrichment helpers ──────────────────────────────────────
# Moved from react_mixin.py — PD-specific context engineering for error
# recovery and path disambiguation.

def _enrich_filesystem_error(
    error_msg: str, failed_path: str, successful_paths: List[str]
) -> str:
    """Enrich filesystem errors with hints from successful prior calls."""
    enrichable_errors = ["ENOENT", "EISDIR", "EACCES", "ENOTDIR"]
    if not any(err in error_msg for err in enrichable_errors):
        return error_msg
    if not successful_paths:
        return error_msg

    failed_basename = failed_path.split('/')[-1] if '/' in failed_path else failed_path
    similar = []
    for p in successful_paths:
        if p.endswith(failed_path) or p.endswith(f"/{failed_path}"):
            similar.append(p)
        elif failed_basename and p.endswith(f"/{failed_basename}"):
            similar.append(p)

    if similar:
        hint = f"\n\nHint: You previously succeeded with: {similar[-1]}"
        hint += f"\nDid you forget the directory prefix?"
        return error_msg + hint
    return error_msg


def _enrich_list_directory_result(result: str, queried_path: str) -> str:
    """Prepend directory path to list_directory entries for unambiguous paths."""
    if not queried_path:
        return result

    lines = result.split('\n')
    enriched = []
    for line in lines:
        if line.startswith('[DIR] '):
            enriched.append(f"[DIR] {queried_path}/{line[6:]}")
        elif line.startswith('[FILE] '):
            enriched.append(f"[FILE] {queried_path}/{line[7:]}")
        elif line.strip():
            enriched.append(f"{queried_path}/{line}")
        else:
            enriched.append(line)
    return '\n'.join(enriched)


class ProjectDirector(BaseSpecialist):
    """
    Autonomous agent for multi-step projects using react_step() MCP.

    PD owns the loop and tool dispatch; prompt-prix owns the LLM call.
    Any specialist can follow this pattern — react_step is a standard MCP
    tool, not a special capability layer.

    Tools: search, browse, list_directory, read_file, create_directory,
    move_file, write_file, run_command.

    See #162 for migration context, ADR-CORE-064 for react_step pattern.
    """

    DEFAULT_MAX_ITERATIONS = 15
    CYCLE_MIN_REPETITIONS = 3

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        # #170: PD gets goal from artifacts, not ProjectContext
        artifacts = state.get("artifacts", {})
        user_request = artifacts.get("user_request", "Unknown request")
        logger.info(f"ProjectDirector starting: {user_request}")

        if not is_react_available(getattr(self, 'external_mcp_client', None)):
            return self._build_error_result(
                "prompt-prix MCP not reachable — cannot execute react_step loop",
                [], {}
            )

        # #203: Read run_id for fork cancellation propagation and mid-loop checks
        run_id = state.get("run_id")
        # ADR-CORE-045: Read fork depth for recursion limit enforcement
        fork_depth = state.get("scratchpad", {}).get("fork_depth", 0)

        # ADR-076: Snapshot artifacts for mid-execution read/write.
        # write_artifact mutates this snapshot; it propagates on return.
        captured_artifacts = artifacts.copy()

        tools = self._build_tools()
        all_params = {**_TOOL_PARAMS, **ARTIFACT_TOOL_PARAMS}
        tool_schemas = build_tool_schemas(tools, all_params)
        task_prompt = self._build_task_prompt(user_request, state)
        model_id = getattr(self.llm_adapter, 'model_name', None) or "default"
        system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
        max_iterations = self._get_max_iterations()

        # #170: Fresh trace each invocation — no resumption from prior runs.
        # Facilitator provides retry context via gathered_context.
        trace: List[Dict[str, Any]] = []
        call_counter = 0
        successful_paths: List[str] = []  # For filesystem error enrichment

        for iteration in range(max_iterations):
            # #203: Check cancellation between react iterations
            if run_id and CancellationManager.is_cancelled(run_id):
                logger.warning(f"ProjectDirector: run {run_id} cancelled at iteration {iteration}")
                return self._build_error_result(
                    f"Run cancelled at iteration {iteration}",
                    trace, captured_artifacts
                )

            try:
                result = call_react_step(
                    self.external_mcp_client,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    task_prompt=task_prompt,
                    trace=trace,
                    tool_schemas=tool_schemas,
                    call_counter=call_counter,
                    timeout=600.0,
                )

                call_counter = result.get("call_counter", call_counter)

                if result.get("completed"):
                    final_response = result.get("final_response", "Task complete.")
                    logger.info(
                        f"ProjectDirector completed after {iteration + 1} iterations, "
                        f"{len(trace)} tool calls"
                    )
                    return self._build_success_result(
                        final_response, trace, captured_artifacts
                    )

                # Dispatch pending tool calls to real MCP services
                pending = result.get("pending_tool_calls", [])
                thought = result.get("thought")

                if not pending:
                    logger.warning("react_step returned incomplete with no pending tool calls")
                    return self._build_error_result(
                        "react_step returned no tool calls and no completion",
                        trace, captured_artifacts
                    )

                for tc in pending:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    observation = self._dispatch_tool_call(
                        tc, tools, successful_paths, captured_artifacts,
                        run_id=run_id, fork_depth=fork_depth,
                    )

                    trace.append({
                        "iteration": iteration,
                        "tool_call": {
                            "id": tc.get("id", f"call_{call_counter}"),
                            "name": tool_name,
                            "args": tool_args,
                        },
                        "observation": observation,
                        "success": not observation.startswith("Error:"),
                        "thought": thought,
                    })

                    # Track successful filesystem paths for error enrichment
                    if not observation.startswith("Error:") and tool_name in (
                        "list_directory", "read_file", "move_file"
                    ):
                        path = tool_args.get("path") or tool_args.get("source")
                        if path:
                            successful_paths.append(path)

                # Stagnation detection after each iteration batch
                if self._check_stagnation(trace):
                    logger.warning("ProjectDirector: stagnation detected in trace")
                    return self._build_stagnation_result(trace, captured_artifacts)

            except Exception as e:
                logger.error(f"ProjectDirector react loop error at iteration {iteration}: {e}")
                return self._build_error_result(
                    f"react loop error at iteration {iteration}: {e}",
                    trace, captured_artifacts
                )

        # Max iterations exceeded
        logger.warning(f"ProjectDirector hit max iterations ({max_iterations})")
        return self._build_partial_result(trace, max_iterations, captured_artifacts)

    # ─── react_step infrastructure ─────────────────────────────────────

    def _dispatch_tool_call(
        self,
        pending: Dict[str, Any],
        tools: Dict[str, ToolDef],
        successful_paths: List[str],
        captured_artifacts: dict,
        run_id: str | None = None,
        fork_depth: int = 0,
    ) -> str:
        """Dispatch a single pending tool call to the appropriate MCP service."""
        tool_name = pending.get("name", "")
        tool_args = pending.get("args", {})
        tool_def = tools.get(tool_name)

        if not tool_def:
            return f"Error: Unknown tool '{tool_name}'"

        if tool_def.is_external:
            # External MCP: filesystem, terminal
            result = dispatch_external_tool(
                self.external_mcp_client, tool_def, tool_args
            )

            # PD-specific enrichments
            if not result.startswith("Error:"):
                if tool_def.function == "list_directory":
                    result = _enrich_list_directory_result(result, tool_args.get("path", ""))
            else:
                if tool_def.service == "filesystem":
                    failed_path = tool_args.get("path") or tool_args.get("source") or ""
                    result = _enrich_filesystem_error(result, failed_path, successful_paths)

            return result

        # fork() — recursive LAS invocation (ADR-045)
        if tool_def.service == "las" and tool_def.function == "fork":
            from ..mcp.fork import dispatch_fork, extract_fork_result
            child_state = dispatch_fork(
                compiled_graph=self._compiled_graph,
                prompt=tool_args.get("prompt", ""),
                context=tool_args.get("context"),
                parent_run_id=run_id,
                fork_depth=fork_depth,
            )
            return extract_fork_result(child_state)

        # Local artifact tools (ADR-076)
        if tool_def.service == "local":
            return dispatch_artifact_tool(tool_name, tool_args, captured_artifacts)

        # Internal MCP: Python-based specialists (search, browse)
        if not hasattr(self, 'mcp_client') or self.mcp_client is None:
            return f"Error: No internal MCP client for service '{tool_def.service}'"
        try:
            raw = self.mcp_client.call(tool_def.service, tool_def.function, **tool_args)
            return str(raw) if not isinstance(raw, str) else raw
        except Exception as e:
            logger.warning(f"ProjectDirector: Tool {tool_name} failed: {e}")
            return f"Error: {e}"

    def _check_stagnation(self, trace: List[Dict[str, Any]]) -> bool:
        """Check trace for repeating tool call patterns indicating stagnation."""
        signatures = []
        for step in trace:
            tc = step.get("tool_call", {})
            signatures.append(
                (tc.get("name", ""), tuple(sorted(tc.get("args", {}).items())))
            )
        period, _pattern = detect_cycle_with_pattern(
            signatures, min_repetitions=self.CYCLE_MIN_REPETITIONS
        )
        return period is not None

    # ─── Tool definitions ──────────────────────────────────────────────

    def _build_tools(self) -> Dict[str, ToolDef]:
        """Define available tools mapping tool names to MCP service coordinates."""
        tools = {
            # Web research (internal MCP)
            "search": ToolDef(
                service="web_specialist", function="search",
                description="Search the web for information. Args: query (str).",
                is_external=False,
            ),
            "browse": ToolDef(
                service="browse_specialist", function="browse",
                description="Fetch and parse a URL to read its content. Args: url (str).",
                is_external=False,
            ),
            # Filesystem (external MCP)
            "list_directory": ToolDef(
                service="filesystem", function="list_directory",
                description="List files and directories. Args: path (str).",
            ),
            "read_file": ToolDef(
                service="filesystem", function="read_file",
                description="Read the contents of a file. Args: path (str).",
            ),
            "create_directory": ToolDef(
                service="filesystem", function="create_directory",
                description="Create a new directory. Args: path (str).",
            ),
            "move_file": ToolDef(
                service="filesystem", function="move_file",
                description="Move or rename a file. Args: source (str), destination (str).",
            ),
            # Terminal (external MCP)
            "run_command": ToolDef(
                service="terminal", function="run_command",
                description="Execute a shell command. Args: command (str). Allowed: mv, mkdir, cp, touch, ls, cat, head, tail, grep, find, wc, sort.",
            ),
        }
        # fork() — recursive LAS invocation (ADR-045)
        tools["fork"] = ToolDef(
            service="las", function="fork",
            description=(
                "Spawn a fresh LAS subagent to handle a subtask with its own "
                "context window. Use when processing multiple independent items "
                "that each need LLM reasoning — each fork gets clean context, "
                "preventing accumulation. The subagent has all the same tools "
                "you do, including fork()."
            ),
            is_external=False,
        )
        # Artifact tools (ADR-076 — read + write artifacts mid-execution)
        tools.update(artifact_tool_defs())
        return tools

    # ─── Prompt & config helpers ───────────────────────────────────────

    def _build_task_prompt(self, user_request: str, state: dict) -> str:
        """Build the task prompt from user request and gathered context.

        #170: Facilitator is the sole context writer. PD receives everything
        it needs via gathered_context — no private knowledge_base or open_questions.
        """
        gathered_context = state.get("artifacts", {}).get("gathered_context", "")

        context_section = ""
        if gathered_context:
            context_section = f"\n**System Context (gathered before your invocation):**\n{gathered_context}\n"
            logger.info("ProjectDirector: Injected gathered_context into prompt")

        return f"**Goal:** {user_request}\n{context_section}"

    def _get_max_iterations(self) -> int:
        """Get max iterations from specialist config."""
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _has_internal_mcp(self, service_name: str) -> bool:
        """Check if an internal MCP service is available."""
        return hasattr(self, 'mcp_client') and self.mcp_client is not None

    # ─── Result builders ───────────────────────────────────────────────

    def _build_success_result(
        self, final_response: str, trace: List[Dict[str, Any]],
        captured_artifacts: dict,
    ) -> Dict[str, Any]:
        return {
            "messages": [AIMessage(content=final_response)],
            "artifacts": dict(captured_artifacts),
            "scratchpad": {
                "specialist_activity": self._summarize_activity(trace),
                "react_trace": trace,
            },
        }

    def _build_error_result(
        self, error_msg: str, trace: List[Dict[str, Any]],
        captured_artifacts: dict,
    ) -> Dict[str, Any]:
        return {
            "messages": [AIMessage(content=error_msg)],
            "artifacts": dict(captured_artifacts),
            "scratchpad": {
                "specialist_activity": self._summarize_activity(trace),
                "react_trace": trace,
            },
        }

    def _build_stagnation_result(
        self, trace: List[Dict[str, Any]],
        captured_artifacts: dict,
    ) -> Dict[str, Any]:
        # Find the repeated pattern for the message
        last_tc = trace[-1].get("tool_call", {}) if trace else {}
        tool_name = last_tc.get("name", "unknown")
        tool_args = last_tc.get("args", {})

        stagnation_message = (
            f"I encountered a problem: I was repeatedly calling '{tool_name}' "
            f"with the same arguments ({tool_args}) without making progress. "
            f"This may indicate the task requires a different approach.\n\n"
            f"Progress before stagnation:\n{self._summarize_trace(trace)}"
        )

        return {
            "messages": [AIMessage(content=stagnation_message)],
            "artifacts": dict(captured_artifacts),
            "signals": {
                "stagnation_detected": True,
                "stagnation_tool": tool_name,
                "stagnation_args": tool_args,
            },
            "scratchpad": {
                "specialist_activity": self._summarize_activity(trace),
                "react_trace": trace,
            },
        }

    def _build_partial_result(
        self, trace: List[Dict[str, Any]], max_iter: int,
        captured_artifacts: dict,
    ) -> Dict[str, Any]:
        partial_msg = self._synthesize_partial(trace, max_iter)

        return {
            "messages": [AIMessage(content=partial_msg)],
            "artifacts": dict(captured_artifacts),
            "signals": {
                "max_iterations_exceeded": True,
            },
            "scratchpad": {
                "specialist_activity": self._summarize_activity(trace),
                "react_trace": trace,
            },
        }

    def _summarize_activity(self, trace: List[Dict[str, Any]]) -> List[str]:
        """
        ADR-073 Phase 3: Summarize trace as human-readable activity entries.

        Written to scratchpad["specialist_activity"] so Facilitator can surface
        prior work on retry. The local trace stays in PD — only this summary
        reaches state.
        """
        entries = []
        for step in trace:
            if not step.get("success"):
                continue
            tc = step.get("tool_call", {})
            name = tc.get("name", "")
            args = tc.get("args", {})

            if name == "create_directory":
                entries.append(f"Created directory {args.get('path', '?')}")
            elif name == "move_file":
                entries.append(f"Moved {args.get('source', '?')} → {args.get('destination', '?')}")
            elif name == "write_file":
                path = args.get("path", "?")
                content = args.get("content", "")
                size = f" ({len(content)} chars)" if content else ""
                entries.append(f"Wrote {path}{size}")
            elif name == "run_command":
                cmd = args.get("command", "?")
                # Truncate long commands (e.g., cat <<EOF writes)
                if len(cmd) > 80:
                    cmd = cmd[:77] + "..."
                entries.append(f"Ran: {cmd}")
        return entries

    def _synthesize_partial(
        self, trace: List[Dict[str, Any]], max_iter: int
    ) -> str:
        """Generate partial synthesis when max iterations exceeded."""
        tool_counts: Dict[str, int] = {}
        for step in trace:
            if step.get("success"):
                name = step.get("tool_call", {}).get("name", "unknown")
                tool_counts[name] = tool_counts.get(name, 0) + 1

        progress_lines = [f"- {name}: {count}" for name, count in tool_counts.items()]

        return (
            f"**Task Incomplete** (reached {max_iter} iteration limit)\n\n"
            f"**Progress ({len(trace)} tool calls):**\n"
            + "\n".join(progress_lines) + "\n\n"
            f"**Last actions:**\n{self._summarize_trace(trace)}"
        )

    def _summarize_trace(self, trace: List[Dict[str, Any]]) -> str:
        """Summarize trace for error/stagnation messages."""
        if not trace:
            return "(no tool calls recorded)"
        lines = []
        for step in trace[-10:]:
            tc = step.get("tool_call", {})
            status = "ok" if step.get("success") else "FAIL"
            lines.append(f"  [{status}] {tc.get('name', '?')}({tc.get('args', {})})")
        return "\n".join(lines)
