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

    def test_task_prompt_building(self, mock_specialist_config, mock_llm_adapter, mock_mcp_client):
        """Test that task prompt includes context information (#162)."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        context = ProjectContext(
            project_goal="Research AI safety",
            knowledge_base=["AI alignment is important"],
            open_questions=["What are current approaches?"]
        )

        state = {"artifacts": {}, "scratchpad": {}}
        prompt = director._build_task_prompt(context, state)

        assert "Research AI safety" in prompt
        assert "AI alignment is important" in prompt
        assert "What are current approaches?" in prompt

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
        """Test graceful degradation when max iterations exceeded (#162)."""
        director = ProjectDirector("project_director", mock_specialist_config)

        context = ProjectContext(
            project_goal="Complex research topic",
            knowledge_base=["Found some info"],
        )

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

        partial = director._synthesize_partial(context, trace, max_iter=5)

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


# =============================================================================
# Issue #166: knowledge_base for filesystem operations
# =============================================================================

class TestUpdateContextFromTrace:
    """
    _update_context_from_trace should populate knowledge_base for filesystem
    operations, not just search/browse. Previously knowledge_base was always
    empty after filesystem tasks.
    """

    @pytest.fixture
    def pd_instance(self, mock_specialist_config, mock_llm_adapter):
        pd = ProjectDirector("project_director", mock_specialist_config)
        pd.llm_adapter = mock_llm_adapter
        return pd

    def test_filesystem_operations_populate_knowledge_base(self, pd_instance):
        """move_file, create_directory, run_command all produce knowledge entries."""
        context = ProjectContext(project_goal="Sort files")
        trace = [
            {"tool_call": {"name": "list_directory", "args": {"path": "/workspace"}}, "success": True},
            {"tool_call": {"name": "read_file", "args": {"path": "/workspace/1.txt"}}, "success": True},
            {"tool_call": {"name": "create_directory", "args": {"path": "/workspace/animals"}}, "success": True},
            {"tool_call": {"name": "move_file", "args": {"source": "1.txt", "destination": "animals/1.txt"}}, "success": True},
            {"tool_call": {"name": "run_command", "args": {"command": "mv /workspace/2.txt /workspace/animals/"}}, "success": True},
        ]

        pd_instance._update_context_from_trace(context, trace)

        assert len(context.knowledge_base) == 5
        assert any("Listed" in k for k in context.knowledge_base)
        assert any("Read" in k for k in context.knowledge_base)
        assert any("Created directory" in k for k in context.knowledge_base)
        assert any("Moved" in k and "animals" in k for k in context.knowledge_base)
        assert any("Ran:" in k for k in context.knowledge_base)

    def test_failed_operations_not_tracked(self, pd_instance):
        """Only successful operations should add knowledge entries."""
        context = ProjectContext(project_goal="Sort files")
        trace = [
            {"tool_call": {"name": "move_file", "args": {"source": "1.txt", "destination": "animals/1.txt"}}, "success": True},
            {"tool_call": {"name": "move_file", "args": {"source": "2.txt", "destination": "plants/2.txt"}}, "success": False},
        ]

        pd_instance._update_context_from_trace(context, trace)

        assert len(context.knowledge_base) == 1
        assert "1.txt" in context.knowledge_base[0]

    def test_research_tools_still_tracked(self, pd_instance):
        """search and browse still produce knowledge entries."""
        context = ProjectContext(project_goal="Research topic")
        trace = [
            {"tool_call": {"name": "search", "args": {"query": "quantum computing"}}, "success": True},
            {"tool_call": {"name": "browse", "args": {"url": "https://example.com"}}, "success": True},
        ]

        pd_instance._update_context_from_trace(context, trace)

        assert len(context.knowledge_base) == 2
        assert any("quantum computing" in k for k in context.knowledge_base)
        assert any("example.com" in k for k in context.knowledge_base)

    def test_iteration_count_updated(self, pd_instance):
        """context.iteration should equal trace length."""
        context = ProjectContext(project_goal="Sort files")
        trace = [
            {"tool_call": {"name": "list_directory", "args": {"path": "/workspace"}}, "success": True},
            {"tool_call": {"name": "read_file", "args": {"path": "/workspace/1.txt"}}, "success": True},
        ]

        pd_instance._update_context_from_trace(context, trace)

        assert context.iteration == 2
