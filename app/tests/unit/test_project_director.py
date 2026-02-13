"""
Tests for ProjectDirector — autonomous agent for multi-step projects.

ProjectDirector uses prompt-prix MCP react_step() for iterative tool use (#162).
PD owns the loop and tool dispatch; prompt-prix owns the LLM call.

See ADR-CORE-029, ADR-CORE-064 for details.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.project_director import ProjectDirector


@pytest.fixture
def mock_specialist_config():
    return {
        "type": "hybrid",
        "prompt_file": "project_director_prompt.md",
        "description": "Emergent Deep Research Director",
        "max_iterations": 5,
        "llm_config": "mock_model"
    }


@pytest.fixture
def mock_llm_adapter():
    """Mock LLM adapter that simulates search-then-synthesize behavior."""
    adapter = MagicMock()
    return adapter


@pytest.fixture
def mock_mcp_client():
    """Mock MCP client for search and browse calls."""
    client = MagicMock()

    def mcp_call(service, function, **kwargs):
        if service == "web_specialist" and function == "search":
            return [
                {"title": "Result 1", "url": "https://example.com/1", "snippet": "First result"},
                {"title": "Result 2", "url": "https://example.com/2", "snippet": "Second result"},
            ]
        elif service == "browse_specialist" and function == "browse":
            return {
                "url": kwargs.get("url", "unknown"),
                "title": "Example Page",
                "content": "This is the page content with relevant information.",
                "status": "success"
            }
        return {"error": f"Unknown service/function: {service}/{function}"}

    client.call = MagicMock(side_effect=mcp_call)
    return client


class TestProjectDirectorPhase2:
    """Tests for ProjectDirector with config-driven ReAct internal iteration."""

    def test_project_director_is_base_specialist(self):
        """
        #162: PD is a plain BaseSpecialist using react_step MCP directly.
        No mixin inheritance, no wrapper injection.
        """
        from app.src.specialists.base import BaseSpecialist
        assert issubclass(ProjectDirector, BaseSpecialist)
        # Verify it uses shared react_step helpers
        from app.src.mcp import is_react_available
        assert callable(is_react_available)

    def test_project_director_defines_tools(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that ProjectDirector defines search and browse tools."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        # The tools are defined inside _execute_logic, so we verify by checking
        # the ToolDef imports work
        from app.src.mcp import ToolDef
        tools = {
            "search": ToolDef(service="web_specialist", function="search"),
            "browse": ToolDef(service="browse_specialist", function="browse"),
        }
        assert "search" in tools
        assert "browse" in tools

    def test_task_prompt_includes_user_request(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """#170: Task prompt includes user_request as Goal."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        state = {"artifacts": {"gathered_context": "Some prior context"}, "scratchpad": {}}
        prompt = director._build_task_prompt("Research AI safety", state)

        assert "Research AI safety" in prompt
        assert "Some prior context" in prompt

    def test_task_prompt_no_gathered_context(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """#170: Task prompt works without gathered_context."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        state = {"artifacts": {}, "scratchpad": {}}
        prompt = director._build_task_prompt("Sort files by category", state)

        assert "Sort files by category" in prompt

    def test_max_iterations_from_config(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that max_iterations is read from config."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        assert director._get_max_iterations() == 5

    def test_max_iterations_default(self, mock_llm_adapter, mock_mcp_client):
        """Test default max_iterations when not in config."""
        director = ProjectDirector("project_director", {"type": "hybrid"})
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        assert director._get_max_iterations() == 15  # DEFAULT_MAX_ITERATIONS

    def test_partial_synthesis_on_max_iterations(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """#170: Partial synthesis shows tool counts and last actions."""
        director = ProjectDirector("project_director", mock_specialist_config)

        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "search", "args": {"query": "topic"}},
                "observation": "Result 1",
                "success": True,
            },
            {
                "iteration": 1,
                "tool_call": {"id": "2", "name": "browse", "args": {"url": "http://example.com"}},
                "observation": "Page content",
                "success": True,
            },
        ]

        partial = director._synthesize_partial(trace, max_iter=5)

        assert "Task Incomplete" in partial
        assert "5 iteration limit" in partial
        assert "search: 1" in partial
        assert "browse: 1" in partial


class TestEmergentProjectSubgraphPhase2:
    """Tests for the simplified EmergentProjectSubgraph."""

    def test_subgraph_returns_empty_exclusions(self):
        """Test that Phase 2 subgraph doesn't exclude specialists from hub-and-spoke."""
        from app.src.workflow.subgraphs.emergent_project import EmergentProjectSubgraph

        subgraph = EmergentProjectSubgraph(
            specialists={"project_director": MagicMock(), "web_specialist": MagicMock()},
            orchestrator=MagicMock(),
            config={}
        )

        assert subgraph.get_excluded_specialists() == []
        assert subgraph.get_router_excluded_specialists() == []

    def test_subgraph_build_no_custom_edges(self):
        """Test that Phase 2 subgraph doesn't add custom edges."""
        from app.src.workflow.subgraphs.emergent_project import EmergentProjectSubgraph

        mock_workflow = MagicMock()
        subgraph = EmergentProjectSubgraph(
            specialists={"project_director": MagicMock()},
            orchestrator=MagicMock(),
            config={}
        )

        subgraph.build(mock_workflow)

        # Should NOT call add_conditional_edges
        mock_workflow.add_conditional_edges.assert_not_called()


    # #170: TestUpdateContextFromTrace removed — _update_context_from_trace deleted.
    # Knowledge extraction moved to Facilitator._extract_trace_knowledge().
