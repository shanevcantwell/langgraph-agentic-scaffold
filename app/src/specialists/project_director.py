import logging
import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
# ADR-CORE-051: ReActMixin removed - capability now injected via config
# ADR-CORE-055: ReActIteration for trace-based serialization
from .mixins import ToolDef, MaxIterationsExceeded, StagnationDetected, ToolResult, ReActIteration
from ..interface.project_context import ProjectContext, ProjectState

logger = logging.getLogger(__name__)


class ProjectDirector(BaseSpecialist):
    """
    Emergent Deep Research controller using config-driven ReAct for internal iteration.

    The LLM decides each iteration whether to:
    - search: Execute web search via MCP
    - browse: Fetch and parse URL content via MCP
    - (no tool call): Synthesize findings and exit loop

    This approach avoids graph-level cycling (ProjectDirector -> WebSpecialist -> ProjectDirector)
    which triggers the 2-step cycle invariant. Instead, the loop is internal to this specialist,
    controlled by max_iterations parameter.

    ADR-CORE-051: ReAct capability is now config-driven instead of mixin inheritance.
    Requires `react: enabled: true` in config.yaml for this specialist.

    See ADR-CORE-029 for architectural details.
    """

    DEFAULT_MAX_ITERATIONS = 15

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Execute emergent deep research using ReAct-style internal iteration.

        The LLM iteratively calls search/browse tools until it has enough
        information to synthesize a final response (indicated by returning
        text without tool calls).
        """
        # Initialize or restore ProjectContext
        project_context = self._get_or_init_context(state)
        logger.info(f"ProjectDirector starting research: {project_context.project_goal}")

        # Define available tools (MCP services)
        # Web tools use internal MCP, filesystem tools use external MCP (containerized)
        tools = {
            # --- Web Research Tools (Internal MCP) ---
            "search": ToolDef(
                service="web_specialist",
                function="search",
                description="Search the web for information. Args: query (str). Returns list of results with title, url, snippet."
            ),
            "browse": ToolDef(
                service="browse_specialist",
                function="browse",
                description="Fetch and parse a URL to read its content. Args: url (str). Returns page title and text content."
            ),
            # --- Filesystem Tools (External MCP) ---
            "list_directory": ToolDef(
                service="filesystem",
                function="list_directory",
                description="List files and directories in a path. Args: path (str). Returns list of entries."
            ),
            "read_file": ToolDef(
                service="filesystem",
                function="read_file",
                description="Read the contents of a file. Args: path (str). Returns file content as string."
            ),
            "create_directory": ToolDef(
                service="filesystem",
                function="create_directory",
                description="Create a new directory. Args: path (str). Creates the directory at the specified path."
            ),
            "move_file": ToolDef(
                service="filesystem",
                function="move_file",
                description="Move or rename a file. Args: source (str), destination (str). Moves file from source to destination."
            ),
            # --- Terminal Tools (External MCP - ADR-MCP-005) ---
            "run_command": ToolDef(
                service="terminal",
                function="run_command",
                description="Execute a shell command. Args: command (str). Only allowlisted commands work (pwd, ls, cat, head, tail, grep, etc.)."
            ),
        }

        # Build the research prompt with current context
        # Issue #75: Include gathered_context from Facilitator
        # ADR-CORE-055: Pass task_prompt string directly (not HumanMessage)
        task_prompt = self._build_research_prompt(project_context, state)

        try:
            # ADR-CORE-055: ReAct loop with trace-based serialization
            # LLM decides tool calls until it returns text-only response
            final_response, trace = self.execute_with_tools(
                task_prompt=task_prompt,
                tools=tools,
                max_iterations=self._get_max_iterations(),
                stop_on_error=False  # Report errors to LLM for adaptive recovery
            )

            # Research complete - update context
            project_context.update_state(ProjectState.COMPLETE)
            self._update_context_from_trace(project_context, trace)

            logger.info(f"ProjectDirector completed research after {len(trace)} tool calls")

            # Issue #91: Use indexed key to preserve traces across invocations
            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=final_response)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    trace_key: [self._serialize_react_iteration(step) for step in trace],
                    "iterations_used": len(trace),
                    "research_status": "complete"
                }
            }

        except StagnationDetected as e:
            # Stagnation: LLM is making the same call repeatedly without progress
            logger.warning(
                f"ProjectDirector stagnation detected: '{e.tool_name}' called "
                f"{e.repeat_count} times with identical args after {e.iterations} iterations"
            )

            project_context.update_state(ProjectState.SYNTHESIZING)
            self._update_context_from_history(project_context, e.history)

            stagnation_message = (
                f"I encountered a problem: I was repeatedly calling '{e.tool_name}' "
                f"with the same arguments ({e.args}) without making progress. "
                f"This may indicate the task requires a different approach.\n\n"
                f"Progress before stagnation:\n"
                f"{self._summarize_tool_history(e.history)}"
            )

            # Issue #91: Use indexed key to preserve traces across invocations
            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=stagnation_message)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    trace_key: [self._serialize_tool_result(h) for h in e.history],
                    "iterations_used": e.iterations,
                    "stagnation_detected": True,
                    "stagnation_tool": e.tool_name,
                    "stagnation_args": e.args,
                    "research_status": "stagnated"
                }
            }

        except MaxIterationsExceeded as e:
            # Graceful degradation: synthesize what we have
            logger.warning(f"ProjectDirector hit max iterations ({e.iterations}), synthesizing partial results")

            project_context.update_state(ProjectState.SYNTHESIZING)
            self._update_context_from_history(project_context, e.history)

            partial_synthesis = self._synthesize_partial(project_context, e.history)

            # Issue #91: Use indexed key to preserve traces across invocations
            trace_key = self._get_trace_key(state)
            return {
                "messages": [AIMessage(content=partial_synthesis)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    trace_key: [self._serialize_tool_result(h) for h in e.history],
                    "iterations_used": e.iterations,
                    "max_iterations_exceeded": True,
                    "research_status": "partial"
                }
            }

    def _get_or_init_context(self, state: dict) -> ProjectContext:
        """Get existing ProjectContext from artifacts or initialize new one."""
        artifacts = state.get("artifacts", {})
        project_context_data = artifacts.get("project_context")

        if project_context_data:
            return ProjectContext(**project_context_data)

        # Read verbatim user request from artifacts (set by state_factory.py)
        user_request = artifacts.get("user_request", "Unknown request")

        context = ProjectContext(project_goal=user_request)
        logger.info(f"Initialized new ProjectContext: {context.project_goal}")
        return context

    def _get_trace_key(self, state: dict) -> str:
        """
        Generate indexed trace key to avoid overwrites (Issue #91).

        Each invocation gets a unique key (research_trace_0, research_trace_1, etc.)
        so subsequent invocations don't overwrite forensic evidence.
        """
        artifacts = state.get("artifacts", {})
        existing_traces = [k for k in artifacts.keys() if k.startswith("research_trace")]
        return f"research_trace_{len(existing_traces)}"

    def _build_research_prompt(self, context: ProjectContext, state: dict) -> str:
        """
        Build the task prompt for the LLM.

        Issue #75: Now includes gathered_context from Facilitator if available.
        This ensures ProjectDirector sees directory listings, file contents, and
        other context gathered before routing.
        """
        # Issue #75: Extract gathered_context from artifacts (set by Facilitator)
        gathered_context = state.get("artifacts", {}).get("gathered_context", "")

        context_section = ""
        if gathered_context:
            context_section = f"""
**System Context (gathered before your invocation):**
{gathered_context}
"""
            logger.info("ProjectDirector: Injected gathered_context into prompt")

        knowledge_section = ""
        if context.knowledge_base:
            knowledge_section = f"""
What I've learned so far:
{chr(10).join(f'- {fact}' for fact in context.knowledge_base)}
"""

        questions_section = ""
        if context.open_questions:
            questions_section = f"""
Open questions to investigate:
{chr(10).join(f'- {q}' for q in context.open_questions)}
"""

        return f"""**Goal:** {context.project_goal}
{context_section}{knowledge_section}{questions_section}
**Available Tools:**
- `search`: Web search (args: query)
- `browse`: Fetch URL content (args: url)
- `list_directory`: List files in a directory (args: path)
- `read_file`: Read file contents (args: path)
- `create_directory`: Create a directory (args: path)
- `move_file`: Move a file (args: source, destination)
- `run_command`: Execute shell command (args: command). For text processing: head, tail, cat, grep, sort, etc.

**Instructions:**
1. Analyze the goal - is this a web research task or a filesystem task?
2. If system context was provided above, USE those paths exactly (they are relative to workspace root)
3. For text extraction (e.g., first character), use `run_command` with shell commands like `head -c1 file.txt`
4. Call the appropriate tools to gather information or perform actions
5. When the goal is complete, provide your final response WITHOUT calling any tools

**Important:** To finish, respond with plain text only (no tool calls). The loop continues as long as you call tools."""

    def _get_max_iterations(self) -> int:
        """
        Get max iterations from config or default.

        ADR-CORE-051: Check _react_config (injected by ReactEnabledSpecialist wrapper)
        first, then fall back to legacy top-level max_iterations config.
        """
        # ADR-CORE-051: Prefer injected _react_config from wrapper
        if hasattr(self, '_react_config') and self._react_config:
            return self._react_config.get('max_iterations', self.DEFAULT_MAX_ITERATIONS)

        # Legacy fallback: top-level max_iterations in specialist_config
        return self.specialist_config.get("max_iterations", self.DEFAULT_MAX_ITERATIONS)

    def _update_context_from_history(self, context: ProjectContext, history: List[ToolResult]) -> None:
        """Update ProjectContext with insights from tool history."""
        for result in history:
            if not result.success:
                continue

            if result.call.name == "search" and result.result:
                # Track that we searched
                query = result.call.args.get("query", "unknown query")
                result_count = len(result.result) if isinstance(result.result, list) else 0
                context.add_knowledge(f"Searched for '{query}' - found {result_count} results")

            elif result.call.name == "browse" and result.result:
                # Track that we browsed
                url = result.call.args.get("url", "unknown url")
                status = result.result.get("status", "unknown") if isinstance(result.result, dict) else "unknown"
                if status == "success":
                    title = result.result.get("title", "Unknown title") if isinstance(result.result, dict) else "Unknown"
                    context.add_knowledge(f"Read '{title}' from {url}")

        context.iteration = len(history)

    def _synthesize_partial(self, context: ProjectContext, history: List[ToolResult]) -> str:
        """Generate partial synthesis when max iterations exceeded."""
        successful_searches = sum(1 for h in history if h.success and h.call.name == "search")
        successful_browses = sum(1 for h in history if h.success and h.call.name == "browse")

        # Collect URLs we successfully browsed
        browsed_urls = []
        for h in history:
            if h.success and h.call.name == "browse" and isinstance(h.result, dict):
                url = h.call.args.get("url", "")
                title = h.result.get("title", "Unknown")
                if url:
                    browsed_urls.append(f"- {title}: {url}")

        sources_section = ""
        if browsed_urls:
            sources_section = f"""

**Sources consulted:**
{chr(10).join(browsed_urls)}
"""

        knowledge_section = ""
        if context.knowledge_base:
            knowledge_section = f"""

**Key findings:**
{chr(10).join(f'- {fact}' for fact in context.knowledge_base[-10:])}
"""

        return f"""**Research Incomplete** (reached maximum iteration limit)

**Goal:** {context.project_goal}

**Progress:**
- Performed {successful_searches} searches
- Read {successful_browses} pages
{knowledge_section}{sources_section}
**Note:** The research iteration limit was reached before a complete synthesis could be formed. You may want to:
1. Ask a more specific question
2. Request the research to continue from where it left off
3. Increase the iteration limit for complex topics"""

    def _serialize_tool_result(self, result: ToolResult) -> Dict[str, Any]:
        """Serialize a ToolResult for artifact storage."""
        return {
            "tool": result.call.name,
            "args": result.call.args,
            "success": result.success,
            "error": result.error,
            # Truncate large results for storage
            "result_preview": str(result.result)[:500] if result.result else None
        }

    def _serialize_react_iteration(self, step: ReActIteration) -> Dict[str, Any]:
        """
        Serialize a ReActIteration for artifact storage.

        ADR-CORE-055: ReActIteration is the canonical trace record from
        trace-based serialization.
        """
        return {
            "iteration": step.iteration,
            "tool": step.tool_call.name,
            "args": step.tool_call.args,
            "success": step.success,
            "thought": step.thought,
            # Truncate large observations for storage
            "observation_preview": step.observation[:500] if step.observation else None
        }

    def _update_context_from_trace(self, context: ProjectContext, trace: List[ReActIteration]) -> None:
        """
        Update ProjectContext with insights from ReAct trace.

        ADR-CORE-055: Works with ReActIteration trace (success path).
        """
        for step in trace:
            if not step.success:
                continue

            if step.tool_call.name == "search":
                # Track that we searched
                query = step.tool_call.args.get("query", "unknown query")
                # Observation contains search results as string
                context.add_knowledge(f"Searched for '{query}'")

            elif step.tool_call.name == "browse":
                # Track that we browsed
                url = step.tool_call.args.get("url", "unknown url")
                context.add_knowledge(f"Read content from {url}")

        context.iteration = len(trace)

    def _summarize_tool_history(self, history: List[ToolResult]) -> str:
        """Summarize tool history for stagnation messages."""
        if not history:
            return "No tool calls completed."

        # Group by tool name
        tool_counts: Dict[str, int] = {}
        successful_results: List[str] = []

        for h in history:
            tool_counts[h.call.name] = tool_counts.get(h.call.name, 0) + 1
            if h.success and h.result:
                # Include first few successful results as context
                if len(successful_results) < 5:
                    result_preview = str(h.result)[:100]
                    successful_results.append(f"- {h.call.name}: {result_preview}...")

        summary_parts = [
            f"Tool calls: {', '.join(f'{name}({count})' for name, count in tool_counts.items())}"
        ]

        if successful_results:
            summary_parts.append("\nSuccessful results:")
            summary_parts.extend(successful_results)

        return "\n".join(summary_parts)
