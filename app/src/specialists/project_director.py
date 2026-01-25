import logging
import json
from typing import Dict, Any, List, Optional

from langchain_core.messages import HumanMessage, AIMessage

from .base import BaseSpecialist
# ADR-CORE-051: ReActMixin removed - capability now injected via config
# Keep ToolDef, MaxIterationsExceeded, ToolResult for type hints and exception handling
from .mixins import ToolDef, MaxIterationsExceeded, ToolResult
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
        tools = {
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
        }

        # Build the research prompt with current context
        research_prompt = self._build_research_prompt(project_context)
        messages = [HumanMessage(content=research_prompt)]

        try:
            # ReAct loop: LLM decides tool calls until it returns text-only response
            final_response, tool_history = self.execute_with_tools(
                messages=messages,
                tools=tools,
                max_iterations=self._get_max_iterations(),
                stop_on_error=False  # Report errors to LLM for adaptive recovery
            )

            # Research complete - update context
            project_context.update_state(ProjectState.COMPLETE)
            self._update_context_from_history(project_context, tool_history)

            logger.info(f"ProjectDirector completed research after {len(tool_history)} tool calls")

            return {
                "messages": [AIMessage(content=final_response)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    "research_trace": [self._serialize_tool_result(h) for h in tool_history],
                    "iterations_used": len(tool_history),
                    "research_status": "complete"
                }
            }

        except MaxIterationsExceeded as e:
            # Graceful degradation: synthesize what we have
            logger.warning(f"ProjectDirector hit max iterations ({e.iterations}), synthesizing partial results")

            project_context.update_state(ProjectState.SYNTHESIZING)
            self._update_context_from_history(project_context, e.history)

            partial_synthesis = self._synthesize_partial(project_context, e.history)

            return {
                "messages": [AIMessage(content=partial_synthesis)],
                "artifacts": {
                    "project_context": project_context.model_dump(),
                    "research_trace": [self._serialize_tool_result(h) for h in e.history],
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

        # Initialize from user request
        messages = state.get("messages", [])
        user_request = messages[-1].content if messages else "Unknown research goal"
        context = ProjectContext(project_goal=user_request)
        logger.info(f"Initialized new ProjectContext: {context.project_goal}")
        return context

    def _build_research_prompt(self, context: ProjectContext) -> str:
        """Build the research context prompt for the LLM."""
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

        return f"""You are a research assistant conducting deep research on the following topic:

**Research Goal:** {context.project_goal}
{knowledge_section}
{questions_section}
**Instructions:**
1. Use the 'search' tool to find relevant information (pass a search query string)
2. Use the 'browse' tool to read specific pages in detail (pass a URL string)
3. Build up your understanding iteratively - search, read results, browse promising links
4. When you have gathered enough information to answer the research goal comprehensively, provide your final synthesis WITHOUT calling any tools

**Your final synthesis should:**
- Directly answer the research goal
- Include specific facts and findings
- Cite sources (URLs) where relevant
- Note any remaining uncertainties or areas needing further research

Begin your research now. If this is your first turn, start with a search query related to the goal."""

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
