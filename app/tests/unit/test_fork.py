"""
Tests for fork() — recursive LAS invocation (ADR-CORE-045).

Tests dispatch_fork() with mocked graph.invoke(), extract_fork_result
fallback chain, depth limiting, CancellationManager integration,
PD integration, and EI integration.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.src.mcp.fork import dispatch_fork, extract_fork_result


class TestDispatchFork:
    """Tests for the dispatch_fork function — direct graph.invoke()."""

    def test_success_returns_final_state(self):
        """dispatch_fork returns the full final state dict from graph.invoke()."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "artifacts": {"final_user_response.md": "Analysis complete."},
            "messages": [],
            "task_is_complete": True,
        }

        result = dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Analyze market landscape",
        )

        assert result["artifacts"]["final_user_response.md"] == "Analysis complete."
        mock_graph.invoke.assert_called_once()

    def test_subagent_flag_in_state(self):
        """dispatch_fork creates state with subagent=True in scratchpad."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(compiled_graph=mock_graph, prompt="Do the thing")

        call_args = mock_graph.invoke.call_args
        initial_state = call_args[0][0]
        assert initial_state["scratchpad"]["subagent"] is True

    def test_context_passed_as_text_to_process(self):
        """dispatch_fork passes context as text_to_process in artifacts."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Analyze this",
            context="Document content here",
        )

        call_args = mock_graph.invoke.call_args
        initial_state = call_args[0][0]
        assert initial_state["artifacts"]["text_to_process"] == "Document content here"

    def test_no_context_omits_text_to_process(self):
        """dispatch_fork omits text_to_process when no context is provided."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(compiled_graph=mock_graph, prompt="Analyze this")

        call_args = mock_graph.invoke.call_args
        initial_state = call_args[0][0]
        assert "text_to_process" not in initial_state["artifacts"]

    def test_depth_limit_returns_error(self):
        """dispatch_fork returns error dict when depth limit reached."""
        mock_graph = MagicMock()

        result = dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Too deep",
            fork_depth=3,
            max_depth=3,
        )

        assert "error" in result
        assert "depth limit" in result["error"].lower()
        mock_graph.invoke.assert_not_called()

    def test_depth_incremented_in_child_state(self):
        """dispatch_fork increments fork_depth in child's scratchpad."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Subtask",
            fork_depth=1,
        )

        call_args = mock_graph.invoke.call_args
        initial_state = call_args[0][0]
        assert initial_state["scratchpad"]["fork_depth"] == 2

    def test_exception_returns_error_dict(self):
        """dispatch_fork returns error dict on graph.invoke() exception."""
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("Graph exploded")

        result = dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Broken task",
        )

        assert "error" in result
        assert "Graph exploded" in result["error"]

    def test_recursion_limit_passed_to_config(self):
        """dispatch_fork passes recursion_limit in graph config."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Task",
            recursion_limit=50,
        )

        call_args = mock_graph.invoke.call_args
        config = call_args[1].get("config") or call_args.kwargs.get("config")
        assert config["recursion_limit"] == 50

    @patch("app.src.mcp.fork.CancellationManager")
    def test_parent_child_registration(self, mock_cm):
        """dispatch_fork registers parent-child relationship when parent_run_id provided."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(
            compiled_graph=mock_graph,
            prompt="Subtask",
            parent_run_id="parent-123",
        )

        mock_cm.register_child.assert_called_once()
        args = mock_cm.register_child.call_args[0]
        assert args[0] == "parent-123"  # parent_run_id
        # child_run_id is a uuid — just check it was passed
        assert len(args[1]) > 0

    @patch("app.src.mcp.fork.CancellationManager")
    def test_no_registration_without_parent_id(self, mock_cm):
        """dispatch_fork skips registration when no parent_run_id."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(compiled_graph=mock_graph, prompt="Top-level fork")

        mock_cm.register_child.assert_not_called()

    @patch("app.src.mcp.fork.CancellationManager")
    def test_cleanup_on_success(self, mock_cm):
        """dispatch_fork clears cancellation state after successful invocation."""
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {"artifacts": {}, "messages": []}

        dispatch_fork(compiled_graph=mock_graph, prompt="Task")

        mock_cm.clear_cancellation.assert_called_once()

    @patch("app.src.mcp.fork.CancellationManager")
    def test_cleanup_on_exception(self, mock_cm):
        """dispatch_fork clears cancellation state even when graph.invoke() raises."""
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("boom")

        dispatch_fork(compiled_graph=mock_graph, prompt="Failing task")

        mock_cm.clear_cancellation.assert_called_once()


class TestExtractForkResult:
    """Tests for extract_fork_result helper — fallback chain priority."""

    def test_error_key_is_highest_priority(self):
        """Error dict from dispatch_fork takes priority."""
        result = extract_fork_result({"error": "Depth limit reached"})
        assert result.startswith("Error:")
        assert "Depth limit reached" in result

    def test_final_user_response_is_canonical(self):
        """final_user_response.md artifact is the canonical result."""
        result = extract_fork_result({
            "artifacts": {
                "final_user_response.md": "Synthesized response",
                "user_request": "original",
            },
            "messages": [MagicMock(content="Raw output")],
        })
        assert result == "Synthesized response"

    def test_error_report_from_scratchpad(self):
        """Error report in scratchpad surfaces when no final_user_response."""
        result = extract_fork_result({
            "artifacts": {},
            "scratchpad": {"error_report": "Circuit breaker triggered"},
            "messages": [],
        })
        assert "Error:" in result
        assert "Circuit breaker triggered" in result

    def test_last_message_fallback(self):
        """Falls back to last message when no artifacts or errors."""
        mock_msg = MagicMock()
        mock_msg.content = "Last specialist output"
        result = extract_fork_result({
            "artifacts": {},
            "scratchpad": {},
            "messages": [MagicMock(content="first"), mock_msg],
        })
        assert result == "Last specialist output"

    def test_empty_response_returns_error(self):
        """Empty state returns error."""
        result = extract_fork_result({
            "artifacts": {},
            "scratchpad": {},
            "messages": [],
        })
        assert result.startswith("Error:")
        assert "empty response" in result

    def test_missing_keys_returns_error(self):
        """Minimal dict with no useful content returns error."""
        result = extract_fork_result({})
        assert result.startswith("Error:")


class TestPDForkIntegration:
    """Tests for fork() integration in ProjectDirector."""

    def test_fork_in_build_tools(self):
        """fork ToolDef is present in PD's tool table."""
        from app.src.specialists.project_director import ProjectDirector

        pd = ProjectDirector("project_director", {
            "type": "llm",
            "max_iterations": 5,
        })
        tools = pd._build_tools()

        assert "fork" in tools
        assert tools["fork"].service == "las"
        assert tools["fork"].function == "fork"
        assert tools["fork"].is_external is False

    def test_fork_in_tool_params(self):
        """fork parameter schema is defined."""
        from app.src.specialists.project_director import _TOOL_PARAMS

        assert "fork" in _TOOL_PARAMS
        assert "prompt" in _TOOL_PARAMS["fork"]["properties"]
        assert "context" in _TOOL_PARAMS["fork"]["properties"]
        assert "prompt" in _TOOL_PARAMS["fork"]["required"]

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_routes_fork(self, mock_dispatch_fork):
        """_dispatch_tool_call routes fork to dispatch_fork with compiled_graph."""
        from app.src.specialists.project_director import ProjectDirector

        mock_dispatch_fork.return_value = {
            "artifacts": {"final_user_response.md": "Subagent result"},
        }

        pd = ProjectDirector("project_director", {
            "type": "llm",
            "max_iterations": 5,
        })
        pd._compiled_graph = MagicMock()
        tools = pd._build_tools()

        pending = {
            "name": "fork",
            "args": {
                "prompt": "Evaluate this proposal",
                "context": "Proposal content here",
            },
        }

        result = pd._dispatch_tool_call(pending, tools, [], {})

        assert result == "Subagent result"
        mock_dispatch_fork.assert_called_once_with(
            compiled_graph=pd._compiled_graph,
            prompt="Evaluate this proposal",
            context="Proposal content here",
            parent_run_id=None,
            fork_depth=0,
        )

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_fork_without_context(self, mock_dispatch_fork):
        """_dispatch_tool_call routes fork correctly when context is omitted."""
        from app.src.specialists.project_director import ProjectDirector

        mock_dispatch_fork.return_value = {
            "artifacts": {"final_user_response.md": "Result"},
        }

        pd = ProjectDirector("project_director", {
            "type": "llm",
            "max_iterations": 5,
        })
        pd._compiled_graph = MagicMock()
        tools = pd._build_tools()

        pending = {
            "name": "fork",
            "args": {"prompt": "Simple task"},
        }

        result = pd._dispatch_tool_call(pending, tools, [], {})

        assert result == "Result"
        mock_dispatch_fork.assert_called_once_with(
            compiled_graph=pd._compiled_graph,
            prompt="Simple task",
            context=None,
            parent_run_id=None,
            fork_depth=0,
        )


class TestEIForkIntegration:
    """Tests for fork() integration in ExitInterviewSpecialist."""

    def test_fork_in_build_tools(self):
        """fork ToolDef is present in EI's tool table."""
        from app.src.specialists.exit_interview_specialist import ExitInterviewSpecialist

        ei = ExitInterviewSpecialist("exit_interview", {"type": "llm"})
        tools = ei._build_tools()

        assert "fork" in tools
        assert tools["fork"].service == "las"
        assert tools["fork"].function == "fork"
        assert tools["fork"].is_external is False

    def test_fork_in_tool_params(self):
        """fork parameter schema is defined in EI's _TOOL_PARAMS."""
        from app.src.specialists.exit_interview_specialist import _TOOL_PARAMS

        assert "fork" in _TOOL_PARAMS
        assert "prompt" in _TOOL_PARAMS["fork"]["properties"]
        assert "context" in _TOOL_PARAMS["fork"]["properties"]
        assert "prompt" in _TOOL_PARAMS["fork"]["required"]

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_routes_fork(self, mock_dispatch_fork):
        """_dispatch_tool routes fork to dispatch_fork with compiled_graph."""
        from app.src.specialists.exit_interview_specialist import ExitInterviewSpecialist

        mock_dispatch_fork.return_value = {
            "artifacts": {"final_user_response.md": "Verification result from subagent"},
        }

        ei = ExitInterviewSpecialist("exit_interview", {"type": "llm"})
        ei._compiled_graph = MagicMock()
        tools = ei._build_tools()

        result = ei._dispatch_tool(
            "fork",
            {"prompt": "Verify file exists at /workspace/output.html", "context": None},
            tools,
            {},  # captured_artifacts
        )

        assert result == "Verification result from subagent"
        mock_dispatch_fork.assert_called_once_with(
            compiled_graph=ei._compiled_graph,
            prompt="Verify file exists at /workspace/output.html",
            context=None,
            parent_run_id=None,
            fork_depth=0,
        )

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_fork_with_context(self, mock_dispatch_fork):
        """_dispatch_tool routes fork with context."""
        from app.src.specialists.exit_interview_specialist import ExitInterviewSpecialist

        mock_dispatch_fork.return_value = {
            "artifacts": {"final_user_response.md": "File verified"},
        }

        ei = ExitInterviewSpecialist("exit_interview", {"type": "llm"})
        ei._compiled_graph = MagicMock()
        tools = ei._build_tools()

        result = ei._dispatch_tool(
            "fork",
            {"prompt": "Check contents", "context": "/workspace/report.md"},
            tools,
            {},
        )

        assert result == "File verified"
        mock_dispatch_fork.assert_called_once_with(
            compiled_graph=ei._compiled_graph,
            prompt="Check contents",
            context="/workspace/report.md",
            parent_run_id=None,
            fork_depth=0,
        )
