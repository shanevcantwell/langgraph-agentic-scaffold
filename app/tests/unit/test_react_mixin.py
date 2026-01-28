# app/tests/unit/test_react_mixin.py
"""
Unit tests for ReActMixin - iterative tool use capability.

Tests cover:
- Happy path: tool calls → final response
- Immediate return when no tools called
- Max iterations exceeded
- Tool error handling
- Unknown tool handling
- Missing dependencies
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.src.specialists.mixins import (
    ReActMixin,
    ToolDef,
    ToolCall,
    ToolResult,
    MaxIterationsExceeded,
    ToolExecutionError,
)


# =============================================================================
# Test Fixtures
# =============================================================================

class MockSpecialistWithReAct(ReActMixin):
    """Mock specialist that uses ReActMixin."""

    def __init__(self):
        self.llm_adapter = MagicMock()
        self.mcp_client = MagicMock()


@pytest.fixture
def specialist():
    """Create a mock specialist with ReActMixin."""
    return MockSpecialistWithReAct()


@pytest.fixture
def basic_tools():
    """Basic tool definitions for testing."""
    return {
        "screenshot": ToolDef(
            service="fara",
            function="screenshot",
            description="Capture a screenshot"
        ),
        "verify": ToolDef(
            service="fara",
            function="verify_element",
            description="Verify an element exists"
        ),
        "click": ToolDef(
            service="fara",
            function="click",
            description="Click at coordinates"
        ),
    }


# =============================================================================
# Schema Tests
# =============================================================================

class TestToolDef:
    """Tests for ToolDef schema."""

    def test_full_name_property(self):
        """Test that full_name returns 'service.function' format."""
        tool = ToolDef(service="fara", function="screenshot")
        assert tool.full_name == "fara.screenshot"

    def test_optional_description(self):
        """Test that description is optional."""
        tool = ToolDef(service="fara", function="click")
        assert tool.description is None


class TestToolCall:
    """Tests for ToolCall schema."""

    def test_basic_creation(self):
        """Test basic ToolCall creation."""
        call = ToolCall(id="call_123", name="screenshot", args={"url": "http://test.com"})
        assert call.id == "call_123"
        assert call.name == "screenshot"
        assert call.args == {"url": "http://test.com"}

    def test_empty_args(self):
        """Test ToolCall with no arguments."""
        call = ToolCall(id="call_456", name="screenshot")
        assert call.args == {}


class TestToolResult:
    """Tests for ToolResult schema."""

    def test_success_result(self):
        """Test successful tool result."""
        call = ToolCall(id="call_123", name="screenshot", args={})
        result = ToolResult(call=call, success=True, result="base64_image_data")
        assert result.success is True
        assert result.result == "base64_image_data"
        assert result.error is None
        assert result.tool_name == "screenshot"

    def test_error_result(self):
        """Test error tool result."""
        call = ToolCall(id="call_456", name="click", args={"x": 100, "y": 200})
        result = ToolResult(call=call, success=False, error="Element not found")
        assert result.success is False
        assert result.result is None
        assert result.error == "Element not found"


# =============================================================================
# ReActMixin Tests - Happy Path
# =============================================================================

class TestReActMixinHappyPath:
    """Tests for successful ReAct execution paths."""

    def test_immediate_final_response_no_tools(self, specialist, basic_tools):
        """Test that LLM returning text (no tools) completes immediately."""
        # Arrange: LLM returns text response, no tool calls
        specialist.llm_adapter.invoke.return_value = {
            "text_response": "The task is complete.",
            "tool_calls": []
        }

        messages = [HumanMessage(content="Check if the button exists")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "The task is complete."
        assert len(history) == 0
        specialist.llm_adapter.invoke.assert_called_once()

    def test_single_tool_call_then_final_response(self, specialist, basic_tools):
        """Test: LLM calls tool → sees result → returns final response."""
        # Arrange: First call returns tool, second call returns final text
        specialist.llm_adapter.invoke.side_effect = [
            {
                "tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]
            },
            {
                "text_response": "Screenshot captured successfully.",
                "tool_calls": []
            }
        ]

        # Mock MCP tool execution
        specialist.mcp_client.call.return_value = "base64_screenshot_data"

        messages = [HumanMessage(content="Take a screenshot")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "Screenshot captured successfully."
        assert len(history) == 1
        assert history[0].success is True
        assert history[0].tool_name == "screenshot"
        assert history[0].result == "base64_screenshot_data"

        # Verify MCP was called correctly
        specialist.mcp_client.call.assert_called_once_with("fara", "screenshot")

    def test_multiple_tool_calls_in_sequence(self, specialist, basic_tools):
        """Test: LLM makes multiple sequential tool calls."""
        # Arrange: 3 iterations - screenshot, verify, then final
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"tool_calls": [{"id": "call_2", "name": "verify", "args": {"description": "Submit button"}}]},
            {"text_response": "Button verified and visible.", "tool_calls": []}
        ]

        specialist.mcp_client.call.side_effect = [
            "screenshot_data",  # screenshot result
            True,  # verify result
        ]

        messages = [HumanMessage(content="Verify the submit button exists")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "Button verified and visible."
        assert len(history) == 2
        assert history[0].tool_name == "screenshot"
        assert history[1].tool_name == "verify"
        assert specialist.llm_adapter.invoke.call_count == 3


# =============================================================================
# ReActMixin Tests - Error Handling
# =============================================================================

class TestReActMixinErrors:
    """Tests for error handling in ReAct execution."""

    def test_max_iterations_exceeded(self, specialist, basic_tools):
        """Test that MaxIterationsExceeded is raised when limit hit."""
        # Arrange: LLM always returns tool calls with different args each time
        # This avoids triggering cycle detection while still testing max_iterations
        call_count = [0]

        def make_unique_call(*args, **kwargs):
            call_count[0] += 1
            return {
                "tool_calls": [{
                    "id": f"call_{call_count[0]}",
                    "name": "screenshot",
                    "args": {"unique_arg": call_count[0]}  # Different args each time
                }]
            }

        specialist.llm_adapter.invoke.side_effect = make_unique_call
        specialist.mcp_client.call.return_value = "screenshot_data"

        messages = [HumanMessage(content="Loop forever")]

        # Act & Assert
        with pytest.raises(MaxIterationsExceeded) as exc_info:
            specialist.execute_with_tools(
                messages=messages,
                tools=basic_tools,
                max_iterations=3
            )

        assert exc_info.value.iterations == 3
        assert len(exc_info.value.history) == 3

    def test_unknown_tool_returns_error_to_llm(self, specialist, basic_tools):
        """Test that unknown tool name is reported as error to LLM."""
        # Arrange: LLM tries to call unknown tool, then gets error, then completes
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "nonexistent_tool", "args": {}}]},
            {"text_response": "I couldn't find that tool, but I'm done.", "tool_calls": []}
        ]

        messages = [HumanMessage(content="Do something")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            max_iterations=10,
            stop_on_error=False  # Report error to LLM, don't raise
        )

        # Assert
        assert len(history) == 1
        assert history[0].success is False
        assert "Unknown tool" in history[0].error
        assert final_response == "I couldn't find that tool, but I'm done."

    def test_tool_execution_error_reported_to_llm(self, specialist, basic_tools):
        """Test that MCP errors are reported to LLM when stop_on_error=False."""
        # Arrange: MCP call fails, LLM handles error and completes
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "click", "args": {"x": 100, "y": 200}}]},
            {"text_response": "Click failed, but I handled it.", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = Exception("Element not clickable")

        messages = [HumanMessage(content="Click the button")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            max_iterations=10,
            stop_on_error=False
        )

        # Assert
        assert len(history) == 1
        assert history[0].success is False
        assert "Element not clickable" in history[0].error
        assert final_response == "Click failed, but I handled it."

    def test_tool_execution_error_raises_when_stop_on_error(self, specialist, basic_tools):
        """Test that MCP errors raise when stop_on_error=True."""
        # Arrange: MCP call fails
        specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"id": "call_1", "name": "click", "args": {"x": 100, "y": 200}}]
        }
        specialist.mcp_client.call.side_effect = Exception("Element not clickable")

        messages = [HumanMessage(content="Click the button")]

        # Act & Assert
        with pytest.raises(ToolExecutionError) as exc_info:
            specialist.execute_with_tools(
                messages=messages,
                tools=basic_tools,
                max_iterations=10,
                stop_on_error=True
            )

        assert exc_info.value.tool_name == "click"
        assert "Element not clickable" in exc_info.value.error


# =============================================================================
# ReActMixin Tests - Dependencies
# =============================================================================

class TestReActMixinDependencies:
    """Tests for dependency requirements."""

    def test_missing_llm_adapter_raises(self, basic_tools):
        """Test that missing llm_adapter raises ValueError."""

        class NoAdapterSpecialist(ReActMixin):
            def __init__(self):
                self.mcp_client = MagicMock()
                # No llm_adapter!

        specialist = NoAdapterSpecialist()
        messages = [HumanMessage(content="Test")]

        with pytest.raises(ValueError, match="llm_adapter"):
            specialist.execute_with_tools(messages, basic_tools)

    def test_missing_mcp_client_returns_error(self, basic_tools):
        """Test that missing mcp_client returns error result."""

        class NoMcpSpecialist(ReActMixin):
            def __init__(self):
                self.llm_adapter = MagicMock()
                self.mcp_client = None  # Explicitly None

        specialist = NoMcpSpecialist()
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"text_response": "Done anyway.", "tool_calls": []}
        ]

        messages = [HumanMessage(content="Test")]

        # Act
        final_response, history = specialist.execute_with_tools(
            messages=messages,
            tools=basic_tools,
            stop_on_error=False
        )

        # Assert: Tool failed due to missing MCP client
        assert len(history) == 1
        assert history[0].success is False
        assert "MCP client not available" in history[0].error


# =============================================================================
# ReActMixin Tests - Message Formatting
# =============================================================================

class TestReActMixinMessageFormatting:
    """Tests for message formatting in the ReAct loop."""

    def test_tool_result_appended_as_tool_message(self, specialist, basic_tools):
        """Test that tool results are formatted as ToolMessage."""
        # Arrange
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"text_response": "Done", "tool_calls": []}
        ]
        specialist.mcp_client.call.return_value = "image_data"

        messages = [HumanMessage(content="Test")]

        # Act
        specialist.execute_with_tools(messages, basic_tools)

        # Assert: Second LLM call should include ToolMessage
        second_call = specialist.llm_adapter.invoke.call_args_list[1]
        request = second_call[0][0]

        # Find the ToolMessage in the messages
        tool_messages = [m for m in request.messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == "image_data"
        assert tool_messages[0].tool_call_id == "call_1"
        assert tool_messages[0].name == "screenshot"

    def test_error_result_formatted_correctly(self, specialist, basic_tools):
        """Test that error results are formatted with 'Error:' prefix."""
        # Arrange
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "click", "args": {}}]},
            {"text_response": "Handled error", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = Exception("Click failed")

        messages = [HumanMessage(content="Test")]

        # Act
        specialist.execute_with_tools(messages, basic_tools, stop_on_error=False)

        # Assert: Second LLM call should include error message
        second_call = specialist.llm_adapter.invoke.call_args_list[1]
        request = second_call[0][0]

        tool_messages = [m for m in request.messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert tool_messages[0].content.startswith("Error:")
        assert "Click failed" in tool_messages[0].content
