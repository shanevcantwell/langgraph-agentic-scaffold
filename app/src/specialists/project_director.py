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
import json
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..utils.cancellation_manager import CancellationManager
from ..utils.progress_store import publish as publish_progress
from ..mcp import (
    ToolDef, is_react_available, call_react_step, build_tool_schemas,
    dispatch_external_tool, artifact_tool_defs, dispatch_artifact_tool,
    ARTIFACT_TOOL_PARAMS, make_terminal_trace_entry,
)
from ..resilience.cycle_detection import detect_cycle_with_pattern

logger = logging.getLogger(__name__)

# #244: Size gate for read_file — encourage delegate() over context-stuffing.
# Only fires at fork_depth == 0 (parent PD). Children have fresh context.
_READ_FILE_SIZE_LIMIT = 2048  # chars (~500 tokens)


# Tool parameter schemas for OpenAI function calling format
_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
    "web_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query string"},
            "limit": {"type": "integer", "description": "Max results (1-20, default 5)"},
        },
        "required": ["query"],
    },
    "web_fetch": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch and extract content from"},
        },
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
    "summarize": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to summarize"},
            "max_length": {"type": "integer", "description": "Max summary length in chars (default 1000)"},
        },
        "required": ["text"],
    },
    "delegate": {
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
            "expected_artifacts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Artifact keys you need back from the subagent. The subagent will be instructed to write results to these keys using write_artifact.",
            },
        },
        "required": ["prompt"],
    },
    # #232: DONE must be in the schema so prompt-prix can intercept it.
    # Empty properties — deliverables go to artifacts via write_artifact.
    "DONE": {
        "type": "object",
        "properties": {},
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
            error_msg = "prompt-prix MCP not reachable — cannot execute react_step loop"
            trace = [make_terminal_trace_entry("ERROR", -1, error_msg, False)]
            return self._build_error_result(error_msg, trace, {})

        # #203: Read run_id for fork cancellation propagation and mid-loop checks
        run_id = state.get("run_id")
        # ADR-CORE-045: Read fork depth for recursion limit enforcement
        fork_depth = state.get("scratchpad", {}).get("fork_depth", 0)

        # Publish start event for live UI progress polling
        if run_id:
            publish_progress(run_id, {
                "specialist": self.specialist_name,
                "iteration": -1,
                "tool": "_start",
                "args_summary": f"goal: {user_request[:150]}",
                "success": True,
            })

        # ADR-076: Snapshot artifacts for mid-execution read/write.
        # write_artifact mutates this snapshot; it propagates on return.
        captured_artifacts = artifacts.copy()

        tools = self._build_tools()
        all_params = {**_TOOL_PARAMS, **ARTIFACT_TOOL_PARAMS}
        tool_schemas = build_tool_schemas(tools, all_params)
        task_prompt = self._build_task_prompt(user_request, state)
        model_id = getattr(self.llm_adapter, 'model_name', None) or "default"
        system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
        api_key = getattr(self.llm_adapter, '_api_key', None)
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
                cancel_msg = f"Run cancelled at iteration {iteration}"
                trace.append(make_terminal_trace_entry("CANCELLED", iteration, cancel_msg, False))
                if run_id:
                    publish_progress(run_id, {
                        "specialist": self.specialist_name, "iteration": iteration,
                        "tool": "CANCELLED", "args_summary": cancel_msg, "success": False,
                    })
                return self._build_error_result(cancel_msg, trace, captured_artifacts)

            try:
                result = call_react_step(
                    self.external_mcp_client,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    task_prompt=task_prompt,
                    trace=trace,
                    tool_schemas=tool_schemas,
                    call_counter=call_counter,
                    api_key=api_key,
                )

                call_counter = result.get("call_counter", call_counter)

                if result.get("completed"):
                    final_response = result.get("final_response", "Task complete.")
                    # #215: Record DONE in trace from prompt-prix done_trace_entry
                    done_entry = result.get("done_trace_entry")
                    if done_entry:
                        done_entry["iteration"] = iteration
                        done_entry["observation"] = final_response
                        done_entry["success"] = True
                        trace.append(done_entry)
                    else:
                        trace.append(make_terminal_trace_entry("DONE", iteration, final_response, True))
                    if run_id:
                        publish_progress(run_id, {
                            "specialist": self.specialist_name, "iteration": iteration,
                            "tool": "DONE", "args_summary": final_response[:200], "success": True,
                        })
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
                    no_tools_msg = "react_step returned no tool calls and no completion"
                    logger.warning(no_tools_msg)
                    trace.append(make_terminal_trace_entry("NO_TOOLS", iteration, no_tools_msg, False))
                    if run_id:
                        publish_progress(run_id, {
                            "specialist": self.specialist_name, "iteration": iteration,
                            "tool": "NO_TOOLS", "args_summary": no_tools_msg, "success": False,
                        })
                    return self._build_error_result(no_tools_msg, trace, captured_artifacts)

                for tc in pending:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})

                    # #250: Publish delegate start event before blocking child run
                    if run_id and tool_name == "delegate":
                        publish_progress(run_id, {
                            "specialist": self.specialist_name,
                            "iteration": iteration,
                            "tool": "delegate",
                            "args_summary": json.dumps(tool_args, default=str)[:200],
                            "success": True,
                            "observation_preview": "Starting child run...",
                        })

                    observation = self._dispatch_tool_call(
                        tc, tools, successful_paths, captured_artifacts,
                        run_id=run_id, fork_depth=fork_depth,
                    )

                    # Build trace entry with optional fork metadata
                    trace_entry = {
                        "iteration": iteration,
                        "tool_call": {
                            "id": tc.get("id", f"call_{call_counter}"),
                            "name": tool_name,
                            "args": tool_args,
                        },
                        "observation": observation,
                        "success": not observation.startswith("Error:"),
                        "thought": thought,
                    }
                    if tool_name == "delegate" and getattr(self, '_last_fork_metadata', None):
                        trace_entry["fork_metadata"] = self._last_fork_metadata
                        self._last_fork_metadata = None
                    trace.append(trace_entry)

                    # Publish progress for live UI polling
                    if run_id:
                        progress_entry = {
                            "specialist": self.specialist_name,
                            "iteration": iteration,
                            "tool": tool_name,
                            "args_summary": json.dumps(tool_args, default=str)[:200],
                            "success": not observation.startswith("Error:"),
                            "observation_preview": observation[:300],
                        }
                        if trace_entry.get("fork_metadata"):
                            progress_entry["fork_metadata"] = trace_entry["fork_metadata"]
                        publish_progress(run_id, progress_entry)

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
                    last_tc = trace[-1].get("tool_call", {}) if trace else {}
                    trace.append(make_terminal_trace_entry(
                        "STAGNATION", iteration,
                        f"Repeating {last_tc.get('name', '?')} with same args — halting",
                        False, {"repeated_tool": last_tc.get("name"), "repeated_args": last_tc.get("args", {})},
                    ))
                    if run_id:
                        publish_progress(run_id, {
                            "specialist": self.specialist_name, "iteration": iteration,
                            "tool": "STAGNATION", "args_summary": f"Repeating {last_tc.get('name', '?')}", "success": False,
                        })
                    return self._build_stagnation_result(trace, captured_artifacts)

            except Exception as e:
                error_msg = f"react loop error at iteration {iteration}: {e}"
                logger.error(f"ProjectDirector {error_msg}")
                trace.append(make_terminal_trace_entry("ERROR", iteration, str(e), False))
                if run_id:
                    publish_progress(run_id, {
                        "specialist": self.specialist_name, "iteration": iteration,
                        "tool": "ERROR", "args_summary": str(e)[:200], "success": False,
                    })
                return self._build_error_result(error_msg, trace, captured_artifacts)

        # Max iterations exceeded
        logger.warning(f"ProjectDirector hit max iterations ({max_iterations})")
        trace.append(make_terminal_trace_entry(
            "MAX_ITERATIONS", max_iterations - 1,
            f"Reached {max_iterations} iterations without completion", False,
            {"max_iterations": max_iterations, "iterations_used": max_iterations},
        ))
        if run_id:
            publish_progress(run_id, {
                "specialist": self.specialist_name, "iteration": max_iterations - 1,
                "tool": "MAX_ITERATIONS", "args_summary": f"Limit: {max_iterations}", "success": False,
            })
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
                # #244: Size gate — nudge parent PD toward delegate() for large files
                elif tool_def.function == "read_file" and fork_depth == 0 and len(result) > _READ_FILE_SIZE_LIMIT:
                    path = tool_args.get("path", "unknown")
                    filename = path.rsplit("/", 1)[-1] if "/" in path else path
                    result = (
                        f"File {path} is too large ({len(result)} chars, ~{len(result) // 4} tokens) "
                        f"to read into this context. "
                        f"Use delegate() to process this file in a separate context. Example:\n"
                        f'delegate(prompt="Process {filename}", context="{path}")'
                    )
            else:
                if tool_def.service == "filesystem":
                    failed_path = tool_args.get("path") or tool_args.get("source") or ""
                    result = _enrich_filesystem_error(result, failed_path, successful_paths)

            return result

        # delegate() — recursive LAS invocation (ADR-045, renamed from fork #225)
        if tool_def.service == "las" and tool_def.function == "delegate":
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
            observation = extract_fork_result(child_state, expected_artifacts=expected)
            # Capture child metadata for trace enrichment + live UI progress
            self._last_fork_metadata = {
                "child_run_id": child_state.get("run_id"),
                "child_routing_history": child_state.get("routing_history", []),
                "had_error": "error" in child_state,
            }
            return observation

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
            # Web research via SearXNG (external MCP — webfetch-mcp, #220/#221)
            "web_search": ToolDef(
                service="webfetch", function="web_search",
                description="Search the web via SearXNG. Args: query (str), limit (int, optional, 1-20, default 5).",
            ),
            "web_fetch": ToolDef(
                service="webfetch", function="web_fetch",
                description="Fetch a URL and extract its content using Mozilla Readability. Args: url (str).",
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
        # summarize() — context hygiene via SummarizerSpecialist MCP (#225)
        tools["summarize"] = ToolDef(
            service="summarizer_specialist", function="summarize",
            description=(
                "Summarize text via LLM. Use to condense web_fetch results or "
                "delegate outputs before writing artifacts. Keeps your context lean."
            ),
            is_external=False,
        )
        # delegate() — recursive LAS invocation (ADR-045, renamed from fork #225)
        tools["delegate"] = ToolDef(
            service="las", function="delegate",
            description=(
                "Hand off an independent subtask to a fresh agent with its own "
                "context window. Use when the subtask needs LLM reasoning and you "
                "only need a summary back — not for deterministic operations "
                "(use run_command instead)."
            ),
            is_external=False,
        )
        # Artifact tools (ADR-076 — read + write artifacts mid-execution)
        tools.update(artifact_tool_defs())
        # #232: DONE must be in tools dict so build_tool_schemas includes it.
        # prompt-prix intercepts DONE before it reaches _dispatch_tool_call.
        tools["DONE"] = ToolDef(
            service="local", function="DONE",
            description="Signal task completion. Call after writing your deliverable to artifacts via write_artifact.",
            is_external=False,
        )
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
        # #225: Structural completion signal — EI reads this instead of re-deriving
        captured_artifacts["completion_signal"] = {
            "status": "COMPLETED",
            "summary": final_response,
        }
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
        # #225: Structural completion signal
        captured_artifacts["completion_signal"] = {
            "status": "ERROR",
            "summary": error_msg,
        }
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
        # Find the repeated tool from the STAGNATION sentinel entry or the
        # preceding trace entry.  The sentinel (appended by the react loop)
        # carries repeated_tool / repeated_args in its args dict.
        last_tc = trace[-1].get("tool_call", {}) if trace else {}
        sentinel_args = last_tc.get("args", {})
        tool_name = sentinel_args.get("repeated_tool") or last_tc.get("name", "unknown")
        tool_args = sentinel_args.get("repeated_args") or sentinel_args

        stagnation_message = (
            f"[Scaffold] Stagnation detected: '{tool_name}' was called "
            f"repeatedly with the same arguments ({tool_args}) without progress. "
            f"The task may require a different approach.\n\n"
            f"Progress before stagnation:\n{self._summarize_trace(trace)}"
        )

        # #225: Structural completion signal
        captured_artifacts["completion_signal"] = {
            "status": "BLOCKED",
            "summary": stagnation_message,
        }
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

        # #225: Structural completion signal
        captured_artifacts["completion_signal"] = {
            "status": "PARTIAL",
            "summary": partial_msg,
        }
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

        Includes both successful and failed steps. Failed steps carry the
        observation text so retry models can learn from prior errors (e.g.,
        allowlist restrictions, missing tools). No truncation — downstream
        can't distinguish missing from cut (#209).
        """
        entries = []
        for step in trace:
            tc = step.get("tool_call", {})
            name = tc.get("name", "")
            args = tc.get("args", {})
            succeeded = step.get("success", False)

            if not succeeded:
                observation = step.get("observation", "unknown error")
                entries.append(f"FAILED: {name}({args}) — {observation}")
                continue

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
