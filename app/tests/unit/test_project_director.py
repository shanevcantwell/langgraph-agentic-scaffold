"""
Tests for ProjectDirector — autonomous agent for multi-step projects.

ProjectDirector uses prompt-prix MCP react_step() for iterative tool use (#162).
PD owns the loop and tool dispatch; prompt-prix owns the LLM call.

See ADR-CORE-029, ADR-CORE-064 for details.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.project_director import ProjectDirector, _TOOL_PARAMS


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


class TestDelegateRename:
    """#225: fork() renamed to delegate() to align with model training data."""

    @pytest.fixture
    def director(self, mock_specialist_config):
        return ProjectDirector("project_director", mock_specialist_config)

    def test_build_tools_has_delegate_not_fork(self, director):
        """_build_tools() includes 'delegate', not 'fork'."""
        tools = director._build_tools()
        assert "delegate" in tools
        assert "fork" not in tools

    def test_delegate_tool_def(self, director):
        """delegate ToolDef points to las service with correct function."""
        tools = director._build_tools()
        td = tools["delegate"]
        assert td.service == "las"
        assert td.function == "delegate"
        assert td.is_external is False


class TestSummarizeTool:
    """#225: summarize() tool for context hygiene."""

    @pytest.fixture
    def director(self, mock_specialist_config):
        return ProjectDirector("project_director", mock_specialist_config)

    def test_build_tools_has_summarize(self, director):
        """_build_tools() includes 'summarize'."""
        tools = director._build_tools()
        assert "summarize" in tools

    def test_summarize_tool_def(self, director):
        """summarize ToolDef points to summarizer_specialist MCP service."""
        tools = director._build_tools()
        td = tools["summarize"]
        assert td.service == "summarizer_specialist"
        assert td.function == "summarize"
        assert td.is_external is False


class TestDoneSchema:
    """#232: DONE must be in PD's tools + params so prompt-prix can intercept it."""

    @pytest.fixture
    def director(self, mock_specialist_config):
        return ProjectDirector("project_director", mock_specialist_config)

    def test_build_tools_has_done(self, director):
        """_build_tools() includes 'DONE'."""
        tools = director._build_tools()
        assert "DONE" in tools

    def test_done_tool_def(self, director):
        """DONE ToolDef is local, not external."""
        tools = director._build_tools()
        td = tools["DONE"]
        assert td.service == "local"
        assert td.function == "DONE"
        assert td.is_external is False

    def test_done_in_tool_params(self):
        """DONE has an entry in _TOOL_PARAMS with empty properties."""
        from app.src.specialists.project_director import _TOOL_PARAMS
        assert "DONE" in _TOOL_PARAMS
        assert _TOOL_PARAMS["DONE"]["properties"] == {}

    def test_done_in_built_schemas(self, director):
        """DONE appears in the schemas sent to prompt-prix."""
        from app.src.mcp.react_step import build_tool_schemas
        from app.src.mcp.artifact_tools import ARTIFACT_TOOL_PARAMS
        tools = director._build_tools()
        all_params = {**_TOOL_PARAMS, **ARTIFACT_TOOL_PARAMS}
        schemas = build_tool_schemas(tools, all_params)
        schema_names = [s["function"]["name"] for s in schemas]
        assert "DONE" in schema_names


class TestCompletionSignal:
    """#225: PD writes completion_signal artifact on all exit paths."""

    @pytest.fixture
    def director(self, mock_specialist_config):
        return ProjectDirector("project_director", mock_specialist_config)

    def test_success_writes_completed_signal(self, director):
        """_build_success_result writes completion_signal with status COMPLETED."""
        captured = {"user_request": "Research AI safety"}
        trace = []

        result = director._build_success_result("All done.", trace, captured_artifacts=captured)

        signal = result["artifacts"]["completion_signal"]
        assert signal["status"] == "COMPLETED"
        assert signal["summary"] == "All done."

    def test_error_writes_error_signal(self, director):
        """_build_error_result writes completion_signal with status ERROR."""
        captured = {"user_request": "Research AI safety"}
        trace = []

        result = director._build_error_result("Connection failed", trace, captured_artifacts=captured)

        signal = result["artifacts"]["completion_signal"]
        assert signal["status"] == "ERROR"
        assert signal["summary"] == "Connection failed"

    def test_stagnation_writes_blocked_signal(self, director):
        """_build_stagnation_result writes completion_signal with status BLOCKED."""
        captured = {"user_request": "Research AI safety"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "web_search", "args": {"query": "AI safety"}},
                "observation": "result",
                "success": True,
            },
        ]

        result = director._build_stagnation_result(trace, captured_artifacts=captured)

        signal = result["artifacts"]["completion_signal"]
        assert signal["status"] == "BLOCKED"
        assert "web_search" in signal["summary"]

    def test_stagnation_reads_sentinel_args(self, director):
        """Stagnation message extracts repeated_tool from STAGNATION sentinel entry."""
        captured = {"user_request": "Research AI safety"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "web_search", "args": {"query": "AI safety"}},
                "observation": "result",
                "success": True,
            },
            {
                "iteration": 1,
                "tool_call": {
                    "id": "terminal", "name": "STAGNATION",
                    "args": {"repeated_tool": "web_search", "repeated_args": {"query": "AI safety"}},
                },
                "observation": "Repeating web_search with same args — halting",
                "success": False,
            },
        ]

        result = director._build_stagnation_result(trace, captured_artifacts=captured)

        signal = result["artifacts"]["completion_signal"]
        summary = signal["summary"]
        # Main message must say "web_search", not "STAGNATION"
        first_line = summary.split("\n")[0]
        assert "web_search" in first_line
        assert "STAGNATION" not in first_line
        assert "Scaffold" in first_line

    def test_partial_writes_partial_signal(self, director):
        """_build_partial_result writes completion_signal with status PARTIAL."""
        captured = {"user_request": "Research AI safety"}
        trace = [
            {
                "iteration": 0,
                "tool_call": {"id": "1", "name": "web_search", "args": {"query": "AI safety"}},
                "observation": "result",
                "success": True,
            },
        ]

        result = director._build_partial_result(trace, max_iter=5, captured_artifacts=captured)

        signal = result["artifacts"]["completion_signal"]
        assert signal["status"] == "PARTIAL"
        assert isinstance(signal["summary"], str)

    def test_completion_signal_coexists_with_other_artifacts(self, director):
        """completion_signal doesn't clobber other captured artifacts."""
        captured = {"user_request": "Sort files", "observations": "important data"}
        trace = []

        result = director._build_success_result("Done!", trace, captured_artifacts=captured)

        assert result["artifacts"]["observations"] == "important data"
        assert result["artifacts"]["user_request"] == "Sort files"
        assert result["artifacts"]["completion_signal"]["status"] == "COMPLETED"


# =============================================================================
# #244: read_file Size Gate (delegate encouragement)
# =============================================================================

class TestReadFileSizeGate:
    """
    #244: Large read_file results at fork_depth==0 are replaced with an error
    message suggesting delegate(). Children (fork_depth>0) get the full result.
    """

    @pytest.fixture
    def director(self, mock_specialist_config):
        pd = ProjectDirector("project_director", mock_specialist_config)
        pd.external_mcp_client = MagicMock()
        return pd

    def test_large_file_at_depth_0_returns_gate_message(self, director):
        """read_file returning >2KB at fork_depth==0 → size gate error with delegate() hint."""
        large_content = "x" * 3000  # 3KB, exceeds _READ_FILE_SIZE_LIMIT
        tools = director._build_tools()
        pending = {"name": "read_file", "args": {"path": "/workspace/docs/ADR-CORE-055.md"}}

        with patch(
            "app.src.specialists.project_director.dispatch_external_tool",
            return_value=large_content,
        ):
            result = director._dispatch_tool_call(
                pending, tools, [], {}, fork_depth=0,
            )

        assert "too large" in result
        assert "delegate()" in result
        assert "ADR-CORE-055.md" in result
        assert large_content not in result  # Content should NOT be returned

    def test_large_file_at_depth_1_returns_full_content(self, director):
        """read_file returning >2KB at fork_depth==1 → full content (child has fresh context)."""
        large_content = "x" * 3000
        tools = director._build_tools()
        pending = {"name": "read_file", "args": {"path": "/workspace/docs/ADR-CORE-055.md"}}

        with patch(
            "app.src.specialists.project_director.dispatch_external_tool",
            return_value=large_content,
        ):
            result = director._dispatch_tool_call(
                pending, tools, [], {}, fork_depth=1,
            )

        assert result == large_content

    def test_small_file_at_depth_0_returns_full_content(self, director):
        """read_file returning <2KB at fork_depth==0 → full content (under threshold)."""
        small_content = "x" * 1000  # 1KB, under limit
        tools = director._build_tools()
        pending = {"name": "read_file", "args": {"path": "/workspace/small.txt"}}

        with patch(
            "app.src.specialists.project_director.dispatch_external_tool",
            return_value=small_content,
        ):
            result = director._dispatch_tool_call(
                pending, tools, [], {}, fork_depth=0,
            )

        assert result == small_content
