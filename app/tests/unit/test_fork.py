"""
Tests for fork() — recursive LAS invocation (ADR-CORE-045).

Tests dispatch_fork() with mocked httpx calls, _extract_result fallback chain,
PD integration, and EI integration.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.src.mcp.fork import dispatch_fork, _extract_result


class TestDispatchFork:
    """Tests for the dispatch_fork function."""

    @patch("app.src.mcp.fork.httpx.post")
    def test_success_extracts_last_message(self, mock_post):
        """fork returns the last message content from the child invocation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "final_output": {
                "messages": [
                    {"content": "First message"},
                    {"content": "Market analysis: competitors include X and Y."},
                ],
                "artifacts": {"user_request": "test"},
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = dispatch_fork(prompt="Analyze market landscape")

        assert result == "Market analysis: competitors include X and Y."
        mock_post.assert_called_once()

    @patch("app.src.mcp.fork.httpx.post")
    def test_subagent_flag_sent(self, mock_post):
        """fork sends subagent: true in request body (not stringly-typed prefix)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "final_output": {"messages": [{"content": "done"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        dispatch_fork(prompt="Do the thing")

        call_args = mock_post.call_args
        request_body = call_args.kwargs.get("json") or call_args[1].get("json")
        # Structural subagent flag — not a string prefix
        assert request_body["subagent"] is True
        # Prompt should be passed unmodified (no [SUBAGENT] prefix)
        assert request_body["input_prompt"] == "Do the thing"

    @patch("app.src.mcp.fork.httpx.post")
    def test_context_passed_as_text_to_process(self, mock_post):
        """fork passes context as text_to_process in the request body."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "final_output": {"messages": [{"content": "result"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        dispatch_fork(prompt="Analyze this", context="Document content here")

        call_args = mock_post.call_args
        request_body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert request_body["text_to_process"] == "Document content here"

    @patch("app.src.mcp.fork.httpx.post")
    def test_no_context_omits_text_to_process(self, mock_post):
        """fork omits text_to_process when no context is provided."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "final_output": {"messages": [{"content": "result"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        dispatch_fork(prompt="Analyze this")

        call_args = mock_post.call_args
        request_body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "text_to_process" not in request_body

    @patch("app.src.mcp.fork.httpx.post")
    def test_timeout_returns_error(self, mock_post):
        """fork returns error string on timeout."""
        import httpx
        mock_post.side_effect = httpx.TimeoutException("timed out")

        result = dispatch_fork(prompt="Slow task", timeout=10.0)

        assert result.startswith("Error:")
        assert "timed out" in result

    @patch("app.src.mcp.fork.httpx.post")
    def test_http_error_returns_error(self, mock_post):
        """fork returns error string on HTTP error."""
        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_post.return_value = mock_response

        result = dispatch_fork(prompt="Broken task")

        assert result.startswith("Error:")
        assert "500" in result

    @patch("app.src.mcp.fork.httpx.post")
    def test_error_report_in_response(self, mock_post):
        """fork surfaces error_report from child invocation."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "final_output": {"error_report": "Circuit breaker triggered"}
        }
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        result = dispatch_fork(prompt="Task that fails")

        assert "Error:" in result
        assert "Circuit breaker triggered" in result


class TestExtractResult:
    """Tests for _extract_result helper — fallback chain priority."""

    def test_error_report_is_highest_priority(self):
        """error_report takes priority over everything else."""
        result = _extract_result({
            "final_output": {
                "error_report": "Child failed",
                "result": "This should be ignored",
                "artifacts": {"final_user_response.md": "Also ignored"},
                "messages": [{"content": "And this"}],
            }
        })
        assert "Error:" in result
        assert "Child failed" in result

    def test_subagent_result_key_preferred_over_artifacts(self):
        """Subagent-mode {"result": "..."} preferred over artifacts."""
        result = _extract_result({
            "final_output": {
                "result": "Concise subagent result",
                "artifacts": {"final_user_response.md": "Longer version"},
                "messages": [{"content": "Message content"}],
            }
        })
        assert result == "Concise subagent result"

    def test_final_user_response_preferred_over_messages(self):
        """final_user_response.md artifact preferred over raw messages."""
        result = _extract_result({
            "final_output": {
                "artifacts": {"final_user_response.md": "Synthesized response"},
                "messages": [{"content": "Raw specialist output"}],
            }
        })
        assert result == "Synthesized response"

    def test_extracts_last_message_dict(self):
        """Falls back to last message when no result key or final_user_response."""
        result = _extract_result({
            "final_output": {
                "messages": [
                    {"content": "first"},
                    {"content": "second"},
                ]
            }
        })
        assert result == "second"

    def test_extracts_message_string(self):
        result = _extract_result({
            "final_output": {
                "messages": ["plain string result"]
            }
        })
        assert result == "plain string result"

    def test_no_artifact_dump(self):
        """Empty messages with artifacts does NOT dump all artifacts."""
        result = _extract_result({
            "final_output": {
                "messages": [],
                "artifacts": {
                    "user_request": "original request",
                    "task_plan": {"plan_summary": "Some plan"},
                    "gathered_context": ["lots of context"],
                }
            }
        })
        # Should return error, NOT dump artifacts
        assert result.startswith("Error:")
        assert "empty response" in result

    def test_empty_response_returns_error(self):
        result = _extract_result({"final_output": {}})
        assert result.startswith("Error:")

    def test_missing_final_output(self):
        result = _extract_result({})
        assert result.startswith("Error:")

    def test_empty_result_key_falls_through(self):
        """Empty string result key falls through to next fallback."""
        result = _extract_result({
            "final_output": {
                "result": "",
                "artifacts": {"final_user_response.md": "Fallback response"},
            }
        })
        assert result == "Fallback response"


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
        """_dispatch_tool_call routes fork to dispatch_fork."""
        from app.src.specialists.project_director import ProjectDirector

        mock_dispatch_fork.return_value = "Subagent result"

        pd = ProjectDirector("project_director", {
            "type": "llm",
            "max_iterations": 5,
        })
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
            prompt="Evaluate this proposal",
            context="Proposal content here",
        )

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_fork_without_context(self, mock_dispatch_fork):
        """_dispatch_tool_call routes fork correctly when context is omitted."""
        from app.src.specialists.project_director import ProjectDirector

        mock_dispatch_fork.return_value = "Result"

        pd = ProjectDirector("project_director", {
            "type": "llm",
            "max_iterations": 5,
        })
        tools = pd._build_tools()

        pending = {
            "name": "fork",
            "args": {"prompt": "Simple task"},
        }

        result = pd._dispatch_tool_call(pending, tools, [], {})

        assert result == "Result"
        mock_dispatch_fork.assert_called_once_with(
            prompt="Simple task",
            context=None,
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
        """_dispatch_tool routes fork to dispatch_fork."""
        from app.src.specialists.exit_interview_specialist import ExitInterviewSpecialist

        mock_dispatch_fork.return_value = "Verification result from subagent"

        ei = ExitInterviewSpecialist("exit_interview", {"type": "llm"})
        tools = ei._build_tools()

        result = ei._dispatch_tool(
            "fork",
            {"prompt": "Verify file exists at /workspace/output.html", "context": None},
            tools,
            {},  # captured_artifacts
        )

        assert result == "Verification result from subagent"
        mock_dispatch_fork.assert_called_once_with(
            prompt="Verify file exists at /workspace/output.html",
            context=None,
        )

    @patch("app.src.mcp.fork.dispatch_fork")
    def test_dispatch_fork_with_context(self, mock_dispatch_fork):
        """_dispatch_tool routes fork with context."""
        from app.src.specialists.exit_interview_specialist import ExitInterviewSpecialist

        mock_dispatch_fork.return_value = "File verified"

        ei = ExitInterviewSpecialist("exit_interview", {"type": "llm"})
        tools = ei._build_tools()

        result = ei._dispatch_tool(
            "fork",
            {"prompt": "Check contents", "context": "/workspace/report.md"},
            tools,
            {},
        )

        assert result == "File verified"
        mock_dispatch_fork.assert_called_once_with(
            prompt="Check contents",
            context="/workspace/report.md",
        )
