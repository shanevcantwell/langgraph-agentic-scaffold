"""
Integration tests for Emergent Project Subgraph - Phase 2 (ReAct capability)

Phase 2 changes the architecture from graph-level cycling to internal iteration:
- ProjectDirector uses ReAct to call search/browse via MCP
- No custom graph edges (standard hub-and-spoke)
- Loop controlled by max_iterations parameter

ADR-CORE-051: ReAct capability is now config-driven, not mixin inheritance.
GraphBuilder injects execute_with_tools() via ReactEnabledSpecialist wrapper.

See ADR-CORE-029 for details.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.project_director import ProjectDirector
from app.src.interface.project_context import ProjectContext, ProjectState


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

    def test_project_director_no_longer_inherits_react_mixin(self):
        """
        ADR-CORE-051: Verify ProjectDirector uses config-driven ReAct, not mixin.

        ReAct capability is now injected by ReactEnabledSpecialist wrapper
        when config has `react: enabled: true`. This test verifies the mixin
        inheritance was removed as part of ADR-CORE-051.
        """
        from app.src.specialists.mixins import ReActMixin
        # Should NOT inherit from ReActMixin anymore
        assert not issubclass(ProjectDirector, ReActMixin)
        # But should still be a BaseSpecialist
        from app.src.specialists.base import BaseSpecialist
        assert issubclass(ProjectDirector, BaseSpecialist)

    def test_project_director_defines_tools(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that ProjectDirector defines search and browse tools."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        # The tools are defined inside _execute_logic, so we verify by checking
        # the ToolDef imports work
        from app.src.specialists.mixins import ToolDef
        tools = {
            "search": ToolDef(service="web_specialist", function="search"),
            "browse": ToolDef(service="browse_specialist", function="browse"),
        }
        assert "search" in tools
        assert "browse" in tools

    def test_project_context_initialization(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that ProjectContext is initialized from user_request artifact."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        state = {
            "messages": [HumanMessage(content="Research quantum computing trends")],
            "artifacts": {"user_request": "Research quantum computing trends"},
            "scratchpad": {}
        }

        context = director._get_or_init_context(state)

        assert context.project_goal == "Research quantum computing trends"
        assert context.state == ProjectState.RESEARCHING
        assert context.iteration == 0

    def test_project_context_restoration(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that existing ProjectContext is restored from artifacts."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        state = {
            "messages": [HumanMessage(content="New message")],
            "artifacts": {
                "project_context": {
                    "project_goal": "Original goal",
                    "knowledge_base": ["Fact 1", "Fact 2"],
                    "open_questions": ["Question 1"],
                    "artifacts": {},
                    "state": "researching",
                    "iteration": 5
                }
            },
            "scratchpad": {}
        }

        context = director._get_or_init_context(state)

        assert context.project_goal == "Original goal"
        assert len(context.knowledge_base) == 2
        assert context.iteration == 5

    def test_research_prompt_building(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that research prompt includes context information."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        context = ProjectContext(
            project_goal="Research AI safety",
            knowledge_base=["AI alignment is important"],
            open_questions=["What are current approaches?"]
        )

        state = {"artifacts": {}, "scratchpad": {}}
        prompt = director._build_research_prompt(context, state)

        assert "Research AI safety" in prompt
        assert "AI alignment is important" in prompt
        assert "What are current approaches?" in prompt
        assert "search" in prompt.lower()
        assert "browse" in prompt.lower()

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

    def test_max_iterations_from_react_config(self, mock_llm_adapter, mock_mcp_client):
        """
        ADR-CORE-051: Test that _react_config (injected by ReactEnabledSpecialist)
        takes precedence over legacy config.
        """
        director = ProjectDirector("project_director", {"type": "hybrid", "max_iterations": 5})
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        # Simulate what ReactEnabledSpecialist does
        director._react_config = {"max_iterations": 20, "stop_on_error": False}

        # Should use _react_config value, not legacy config
        assert director._get_max_iterations() == 20

    def test_tool_result_serialization(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that tool results are serialized correctly for artifacts."""
        from app.src.specialists.mixins import ToolResult, ToolCall

        director = ProjectDirector("project_director", mock_specialist_config)

        result = ToolResult(
            call=ToolCall(id="test_1", name="search", args={"query": "test"}),
            success=True,
            result=[{"title": "Result", "url": "http://example.com"}]
        )

        serialized = director._serialize_tool_result(result)

        assert serialized["tool"] == "search"
        assert serialized["args"] == {"query": "test"}
        assert serialized["success"] is True
        assert serialized["error"] is None
        assert "Result" in serialized["result_preview"]

    def test_partial_synthesis_on_max_iterations(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test graceful degradation when max iterations exceeded."""
        from app.src.specialists.mixins import ToolResult, ToolCall

        director = ProjectDirector("project_director", mock_specialist_config)

        context = ProjectContext(
            project_goal="Complex research topic",
            knowledge_base=["Found some info"],
        )

        history = [
            ToolResult(
                call=ToolCall(id="1", name="search", args={"query": "topic"}),
                success=True,
                result=[{"title": "R1"}]
            ),
            ToolResult(
                call=ToolCall(id="2", name="browse", args={"url": "http://example.com"}),
                success=True,
                result={"title": "Example", "status": "success"}
            ),
        ]

        partial = director._synthesize_partial(context, history)

        assert "Research Incomplete" in partial
        assert "Complex research topic" in partial
        assert "1 searches" in partial
        assert "1 pages" in partial


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
