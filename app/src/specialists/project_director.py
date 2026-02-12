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
from ..interface.project_context import ProjectContext, ProjectState
from ..mcp import (
    ToolDef, is_react_available, call_react_step, build_tool_schemas,
    dispatch_external_tool,
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
        project_context = self._get_or_init_context(state)
        logger.info(f"ProjectDirector starting: {project_context.project_goal}")

        if not is_react_available(getattr(self, 'external_mcp_client', None)):
            return self._build_error_result(
                project_context,
                "prompt-prix MCP not reachable — cannot execute react_step loop", []
            )

        tools = self._build_tools()
        tool_schemas = build_tool_schemas(tools, _TOOL_PARAMS)
        task_prompt = self._build_task_prompt(project_context, state)
        model_id = getattr(self.llm_adapter, 'model_name', None) or "default"
        system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
        max_iterations = self._get_max_iterations()

        # ADR-CORE-059: Resume from prior trace if available (Memento fix)
        trace: List[Dict[str, Any]] = self._load_resume_trace(state.get("artifacts", {}))
        call_counter = len(trace)
        successful_paths: List[str] = []  # For filesystem error enrichment

        if trace:
            logger.info(f"ProjectDirector: Resuming from {len(trace)} prior trace entries")

        for iteration in range(max_iterations):
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
                    project_context.update_state(ProjectState.COMPLETE)
                    self._update_context_from_trace(project_context, trace)
                    logger.info(
                        f"ProjectDirector completed after {iteration + 1} iterations, "
                        f"{len(trace)} tool calls"
                    )
                    return self._build_success_result(
                        project_context, final_response, trace
                    )

                # Dispatch pending tool calls to real MCP services
                pending = result.get("pending_tool_calls", [])
                thought = result.get("thought")

                if not pending:
                    logger.warning("react_step returned incomplete with no pending tool calls")
                    return self._build_error_result(
                        project_context,
                        "react_step returned no tool calls and no completion", trace
                    )

                for tc in pending:
                    tool_name = tc.get("name", "unknown")
                    tool_args = tc.get("args", {})
                    observation = self._dispatch_tool_call(tc, tools, successful_paths)

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
                    project_context.update_state(ProjectState.SYNTHESIZING)
                    self._update_context_from_trace(project_context, trace)
                    return self._build_stagnation_result(project_context, trace)

            except Exception as e:
                logger.error(f"ProjectDirector react loop error at iteration {iteration}: {e}")
                return self._build_error_result(
                    project_context,
                    f"react loop error at iteration {iteration}: {e}", trace
                )

        # Max iterations exceeded
        project_context.update_state(ProjectState.SYNTHESIZING)
        self._update_context_from_trace(project_context, trace)
        logger.warning(f"ProjectDirector hit max iterations ({max_iterations})")
        return self._build_partial_result(project_context, trace, max_iterations)

    # ─── react_step infrastructure ─────────────────────────────────────

    def _dispatch_tool_call(
        self,
        pending: Dict[str, Any],
        tools: Dict[str, ToolDef],
        successful_paths: List[str],
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
        return {
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

    # ─── Prompt & config helpers ───────────────────────────────────────

    def _build_task_prompt(self, context: ProjectContext, state: dict) -> str:
        """Build the task prompt from ProjectContext and gathered context."""
        gathered_context = state.get("artifacts", {}).get("gathered_context", "")

        context_section = ""
        if gathered_context:
            context_section = f"\n**System Context (gathered before your invocation):**\n{gathered_context}\n"
            logger.info("ProjectDirector: Injected gathered_context into prompt")

        knowledge_section = ""
        if context.knowledge_base:
            knowledge_section = (
                "\nWhat I've learned so far:\n"
                + "\n".join(f"- {fact}" for fact in context.knowledge_base)
                + "\n"
            )

        questions_section = ""
        if context.open_questions:
            questions_section = (
                "\nOpen questions to investigate:\n"
                + "\n".join(f"- {q}" for q in context.open_questions)
                + "\n"
            )

        return f"**Goal:** {context.project_goal}\n{context_section}{knowledge_section}{questions_section}"

    def _get_max_iterations(self) -> int:
        """Get max iterations from specialist config."""
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _has_internal_mcp(self, service_name: str) -> bool:
        """Check if an internal MCP service is available."""
        return hasattr(self, 'mcp_client') and self.mcp_client is not None

    # ─── Resume trace (ADR-CORE-059 Memento fix) ──────────────────────

    def _load_resume_trace(self, artifacts: dict) -> List[Dict[str, Any]]:
        """
        Load resume_trace artifact as list of dicts.

        Facilitator assembles prior traces into resume_trace artifact.
        The trace format is already dicts — same format react_step uses.
        """
        resume_trace = artifacts.get("resume_trace")
        if not resume_trace or not isinstance(resume_trace, list):
            return []

        valid = []
        for entry in resume_trace:
            if not isinstance(entry, dict):
                continue
            # Normalize: ensure tool_call dict exists
            if "tool_call" not in entry and "tool" in entry:
                entry = {
                    "iteration": entry.get("iteration", len(valid)),
                    "tool_call": {
                        "id": entry.get("id", f"resume_{len(valid)}"),
                        "name": entry.get("tool", "unknown"),
                        "args": entry.get("args", {}),
                    },
                    "observation": entry.get("observation_preview") or entry.get("observation", ""),
                    "success": entry.get("success", True),
                    "thought": entry.get("thought"),
                }
            valid.append(entry)

        if valid:
            logger.info(f"ProjectDirector: Loaded {len(valid)} resume trace entries")
        return valid

    # ─── ProjectContext tracking ───────────────────────────────────────

    def _get_or_init_context(self, state: dict) -> ProjectContext:
        """Get existing ProjectContext from artifacts or initialize new one."""
        artifacts = state.get("artifacts", {})
        project_context_data = artifacts.get("project_context")

        if project_context_data:
            return ProjectContext(**project_context_data)

        user_request = artifacts.get("user_request", "Unknown request")
        context = ProjectContext(project_goal=user_request)
        logger.info(f"Initialized new ProjectContext: {context.project_goal}")
        return context

    def _update_context_from_trace(
        self, context: ProjectContext, trace: List[Dict[str, Any]]
    ) -> None:
        """Update ProjectContext with insights from trace dicts."""
        for step in trace:
            if not step.get("success"):
                continue
            tc = step.get("tool_call", {})
            name = tc.get("name", "")
            args = tc.get("args", {})

            # Research tools
            if name == "search":
                context.add_knowledge(f"Searched for '{args.get('query', '?')}'")
            elif name == "browse":
                context.add_knowledge(f"Read content from {args.get('url', '?')}")
            # Filesystem tools (#166)
            elif name == "list_directory":
                context.add_knowledge(f"Listed {args.get('path', '?')}")
            elif name == "read_file":
                context.add_knowledge(f"Read {args.get('path', '?')}")
            elif name == "create_directory":
                context.add_knowledge(f"Created directory {args.get('path', '?')}")
            elif name == "move_file":
                context.add_knowledge(
                    f"Moved {args.get('source', '?')} → {args.get('destination', '?')}"
                )
            elif name == "run_command":
                context.add_knowledge(f"Ran: {args.get('command', '?')}")

        context.iteration = len(trace)

    # ─── Result builders ───────────────────────────────────────────────

    def _build_success_result(
        self, context: ProjectContext,
        final_response: str, trace: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "messages": [AIMessage(content=final_response)],
            "artifacts": {
                "project_context": context.model_dump(),
                "resume_trace": trace,
                "iterations_used": len(trace),
                "research_status": "complete",
            },
        }

    def _build_error_result(
        self, context: ProjectContext,
        error_msg: str, trace: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return {
            "messages": [AIMessage(content=error_msg)],
            "artifacts": {
                "project_context": context.model_dump(),
                "resume_trace": trace,
                "iterations_used": len(trace),
                "research_status": "error",
            },
        }

    def _build_stagnation_result(
        self, context: ProjectContext,
        trace: List[Dict[str, Any]]
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
            "artifacts": {
                "project_context": context.model_dump(),
                "resume_trace": trace,
                "iterations_used": len(trace),
                "stagnation_detected": True,
                "stagnation_tool": tool_name,
                "stagnation_args": tool_args,
                "research_status": "stagnated",
            },
        }

    def _build_partial_result(
        self, context: ProjectContext,
        trace: List[Dict[str, Any]], max_iter: int
    ) -> Dict[str, Any]:
        partial_msg = self._synthesize_partial(context, trace, max_iter)
        return {
            "messages": [AIMessage(content=partial_msg)],
            "artifacts": {
                "project_context": context.model_dump(),
                "resume_trace": trace,
                "iterations_used": max_iter,
                "max_iterations_exceeded": True,
                "research_status": "partial",
            },
        }

    def _synthesize_partial(
        self, context: ProjectContext, trace: List[Dict[str, Any]], max_iter: int
    ) -> str:
        """Generate partial synthesis when max iterations exceeded."""
        successful_searches = sum(
            1 for s in trace
            if s.get("success") and s.get("tool_call", {}).get("name") == "search"
        )
        successful_browses = sum(
            1 for s in trace
            if s.get("success") and s.get("tool_call", {}).get("name") == "browse"
        )

        knowledge_section = ""
        if context.knowledge_base:
            knowledge_section = (
                "\n\n**Key findings:**\n"
                + "\n".join(f"- {fact}" for fact in context.knowledge_base[-10:])
            )

        return (
            f"**Research Incomplete** (reached maximum iteration limit)\n\n"
            f"**Goal:** {context.project_goal}\n\n"
            f"**Progress:**\n"
            f"- Performed {successful_searches} searches\n"
            f"- Read {successful_browses} pages"
            f"{knowledge_section}\n\n"
            f"**Note:** The research iteration limit was reached before a complete "
            f"synthesis could be formed."
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
