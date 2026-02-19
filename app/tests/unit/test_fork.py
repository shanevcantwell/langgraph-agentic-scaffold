"""
Tests for fork() — recursive LAS invocation (ADR-CORE-045).

Tests dispatch_fork() with mocked httpx calls and PD integration.
"""
import pytest
from unittest.mock import patch, MagicMock

from app.src.mcp.fork import dispatch_fork, _extract_result, _SUBAGENT_PREFIX


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
    def test_subagent_prefix_prepended(self, mock_post):
        """fork prepends the subagent marker to the prompt."""
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
        assert request_body["input_prompt"].startswith("[SUBAGENT]")
        assert "Do the thing" in request_body["input_prompt"]

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
    """Tests for _extract_result helper."""

    def test_extracts_last_message_dict(self):
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

    def test_falls_back_to_artifacts(self):
        result = _extract_result({
            "final_output": {
                "messages": [],
                "artifacts": {
                    "user_request": "original request",
                    "evaluation": "The product is viable.",
                }
            }
        })
        assert "evaluation" in result
        assert "The product is viable." in result
        assert "user_request" not in result  # System artifact filtered

    def test_empty_response_returns_error(self):
        result = _extract_result({"final_output": {}})
        assert result.startswith("Error:")

    def test_missing_final_output(self):
        result = _extract_result({})
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
