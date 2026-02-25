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
    """Mock MCP client."""
    client = MagicMock()
    client.call = MagicMock(return_value={"error": "Unknown service/function"})
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
        """Test that ProjectDirector defines web_search and web_fetch tools (#220, #221)."""
        director = ProjectDirector("project_director", mock_specialist_config)
        director.llm_adapter = mock_llm_adapter
        director.mcp_client = mock_mcp_client

        tools = director._build_tools()
        assert "web_search" in tools
        assert "web_fetch" in tools
        assert tools["web_search"].service == "webfetch"
        assert tools["web_fetch"].service == "webfetch"

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
                "tool_call": {"id": "1", "name": "web_search", "args": {"query": "topic"}},
                "observation": "Result 1",
                "success": True,
            },
            {
                "iteration": 1,
                "tool_call": {"id": "2", "name": "web_fetch", "args": {"url": "http://example.com"}},
                "observation": "Page content",
                "success": True,
            },
        ]

        partial = director._synthesize_partial(trace, max_iter=5)

        assert "Task Incomplete" in partial
        assert "5 iteration limit" in partial
        assert "web_search: 1" in partial
        assert "web_fetch: 1" in partial


class TestEmergentProjectSubgraphPhase2:
    """Tests for the simplified EmergentProjectSubgraph."""

    def test_subgraph_returns_empty_exclusions(self):
        """Test that Phase 2 subgraph doesn't exclude specialists from hub-and-spoke."""
        from app.src.workflow.subgraphs.emergent_project import EmergentProjectSubgraph

        subgraph = EmergentProjectSubgraph(
            specialists={"project_director": MagicMock()},
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


class TestArtifactPropagation:
    """ADR-076: Captured artifacts propagate through all result builders."""

    @pytest.fixture
    def director(self, mock_specialist_config):
        return ProjectDirector("project_director", mock_specialist_config)

    def test_partial_result_includes_captured_artifacts(self, director):
        """Written artifacts survive max_iterations via _build_partial_result."""
        captured = {"user_request": "Sort files", "observations": "1.txt is about dolphins"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "read_file", "args": {"path": "/test/1.txt"}},
                "observation": "dolphin content",
                "success": True,
            },
        ]

        result = director._build_partial_result(trace, max_iter=5, captured_artifacts=captured)

        assert result["artifacts"]["observations"] == "1.txt is about dolphins"
        assert result["artifacts"]["user_request"] == "Sort files"
        # ADR-077: max_iterations_exceeded is a routing signal, not an artifact
        assert result["signals"]["max_iterations_exceeded"] is True

    def test_success_result_includes_captured_artifacts(self, director):
        """Written artifacts propagate on normal completion."""
        captured = {"user_request": "Sort files", "progress": "8 of 13 done"}
        trace = []

        result = director._build_success_result("Done!", trace, captured_artifacts=captured)

        assert result["artifacts"]["progress"] == "8 of 13 done"
        assert result["artifacts"]["user_request"] == "Sort files"

    def test_error_result_includes_captured_artifacts(self, director):
        """Written artifacts survive even on error."""
        captured = {"user_request": "Sort files", "partial_work": "started"}
        trace = []

        result = director._build_error_result("Something broke", trace, captured_artifacts=captured)

        assert result["artifacts"]["partial_work"] == "started"

    def test_stagnation_result_includes_captured_artifacts(self, director):
        """Written artifacts survive stagnation detection."""
        captured = {"user_request": "Sort files"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "read_file", "args": {"path": "/x"}},
                "observation": "content",
                "success": True,
            },
        ]

        result = director._build_stagnation_result(trace, captured_artifacts=captured)

        assert result["artifacts"]["user_request"] == "Sort files"
        # ADR-077: stagnation_detected is a routing signal, not an artifact
        assert result["signals"]["stagnation_detected"] is True

    def test_stagnation_signals_separate_from_artifacts(self, director):
        """ADR-077: Stagnation signals don't pollute the artifacts dict."""
        captured = {"user_request": "Sort", "my_notes": "important observations"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "search", "args": {"query": "x"}},
                "observation": "result",
                "success": True,
            },
        ]

        result = director._build_stagnation_result(trace, captured_artifacts=captured)

        assert result["artifacts"]["my_notes"] == "important observations"
        assert "stagnation_detected" not in result["artifacts"]
        assert result["signals"]["stagnation_detected"] is True

    def test_build_tools_includes_artifact_tools(self, director):
        """ADR-076: PD's tool set includes artifact read/write tools."""
        tools = director._build_tools()
        assert "list_artifacts" in tools
        assert "retrieve_artifact" in tools
        assert "write_artifact" in tools
        assert tools["write_artifact"].is_external is False
        assert tools["write_artifact"].service == "local"
