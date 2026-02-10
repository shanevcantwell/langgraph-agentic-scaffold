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
- ADR-CORE-055: Trace-based serialization includes AIMessage with tool_calls
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from app.src.specialists.mixins import (
    ReActMixin,
    ToolDef,
    ToolCall,
    ToolResult,
    ReActIteration,  # ADR-CORE-055
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


class TestReActIteration:
    """Tests for ReActIteration schema (ADR-CORE-055)."""

    def test_successful_iteration(self):
        """Test creating a successful iteration record."""
        call = ToolCall(id="call_123", name="screenshot", args={})
        iteration = ReActIteration(
            iteration=0,
            tool_call=call,
            observation="base64_image_data",
            success=True
        )
        assert iteration.iteration == 0
        assert iteration.tool_call.name == "screenshot"
        assert iteration.observation == "base64_image_data"
        assert iteration.success is True
        assert iteration.thought is None

    def test_failed_iteration(self):
        """Test creating a failed iteration record."""
        call = ToolCall(id="call_456", name="click", args={"x": 100, "y": 200})
        iteration = ReActIteration(
            iteration=1,
            tool_call=call,
            observation="Error: Element not found",
            success=False,
            thought="I'll try clicking the button"
        )
        assert iteration.iteration == 1
        assert iteration.success is False
        assert "Error:" in iteration.observation
        assert iteration.thought == "I'll try clicking the button"


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

        # ADR-CORE-055: Use task_prompt string instead of messages list
        task_prompt = "Check if the button exists"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "The task is complete."
        assert len(trace) == 0
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

        task_prompt = "Take a screenshot"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "Screenshot captured successfully."
        assert len(trace) == 1
        # ADR-CORE-055: ReActIteration has observation, not result
        assert trace[0].success is True
        assert trace[0].tool_call.name == "screenshot"
        assert trace[0].observation == "base64_screenshot_data"

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

        task_prompt = "Verify the submit button exists"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            max_iterations=10
        )

        # Assert
        assert final_response == "Button verified and visible."
        assert len(trace) == 2
        assert trace[0].tool_call.name == "screenshot"
        assert trace[1].tool_call.name == "verify"
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

        task_prompt = "Loop forever"

        # Act & Assert
        with pytest.raises(MaxIterationsExceeded) as exc_info:
            specialist.execute_with_tools(
                task_prompt=task_prompt,
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

        task_prompt = "Do something"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            max_iterations=10,
            stop_on_error=False  # Report error to LLM, don't raise
        )

        # Assert
        assert len(trace) == 1
        assert trace[0].success is False
        assert "Unknown tool" in trace[0].observation
        assert final_response == "I couldn't find that tool, but I'm done."

    def test_tool_execution_error_reported_to_llm(self, specialist, basic_tools):
        """Test that MCP errors are reported to LLM when stop_on_error=False."""
        # Arrange: MCP call fails, LLM handles error and completes
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "click", "args": {"x": 100, "y": 200}}]},
            {"text_response": "Click failed, but I handled it.", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = Exception("Element not clickable")

        task_prompt = "Click the button"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            max_iterations=10,
            stop_on_error=False
        )

        # Assert
        assert len(trace) == 1
        assert trace[0].success is False
        assert "Element not clickable" in trace[0].observation
        assert final_response == "Click failed, but I handled it."

    def test_tool_execution_error_raises_when_stop_on_error(self, specialist, basic_tools):
        """Test that MCP errors raise when stop_on_error=True."""
        # Arrange: MCP call fails
        specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"id": "call_1", "name": "click", "args": {"x": 100, "y": 200}}]
        }
        specialist.mcp_client.call.side_effect = Exception("Element not clickable")

        task_prompt = "Click the button"

        # Act & Assert
        with pytest.raises(ToolExecutionError) as exc_info:
            specialist.execute_with_tools(
                task_prompt=task_prompt,
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
        task_prompt = "Test"

        with pytest.raises(ValueError, match="llm_adapter"):
            specialist.execute_with_tools(task_prompt, basic_tools)

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

        task_prompt = "Test"

        # Act
        final_response, trace = specialist.execute_with_tools(
            task_prompt=task_prompt,
            tools=basic_tools,
            stop_on_error=False
        )

        # Assert: Tool failed due to missing MCP client
        assert len(trace) == 1
        assert trace[0].success is False
        assert "MCP client not available" in trace[0].observation


# =============================================================================
# ReActMixin Tests - Message Formatting (ADR-CORE-055)
# =============================================================================

class TestReActMixinMessageFormatting:
    """Tests for message formatting in the ReAct loop (ADR-CORE-055)."""

    def test_ai_message_with_tool_calls_included_in_chain(self, specialist, basic_tools):
        """
        ADR-CORE-055: Verify AIMessage with tool_calls is included in message chain.

        This is THE core fix for Issue #88 - previously the LLM's decision
        (AIMessage with tool_calls) was NOT being included, only ToolMessage.
        """
        # Arrange
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"text_response": "Done", "tool_calls": []}
        ]
        specialist.mcp_client.call.return_value = "image_data"

        task_prompt = "Test"

        # Act
        specialist.execute_with_tools(task_prompt, basic_tools)

        # Assert: Second LLM call should include BOTH AIMessage (decision) AND ToolMessage (result)
        second_call = specialist.llm_adapter.invoke.call_args_list[1]
        request = second_call[0][0]

        # Find the AIMessage with tool_calls
        ai_messages = [m for m in request.messages if isinstance(m, AIMessage)]
        assert len(ai_messages) == 1, "ADR-CORE-055: AIMessage with tool_calls must be included"
        assert ai_messages[0].tool_calls is not None
        assert len(ai_messages[0].tool_calls) == 1
        assert ai_messages[0].tool_calls[0]["name"] == "screenshot"

        # Find the ToolMessage with result
        tool_messages = [m for m in request.messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == "image_data"
        assert tool_messages[0].tool_call_id == "call_1"
        assert tool_messages[0].name == "screenshot"

    def test_message_chain_order_preserved(self, specialist, basic_tools):
        """
        ADR-CORE-055: Verify message chain maintains correct order:
        HumanMessage → AIMessage (tool_call 1) → ToolMessage (result 1) →
        AIMessage (tool_call 2) → ToolMessage (result 2) → ...
        """
        # Arrange: Two tool calls in sequence
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"tool_calls": [{"id": "call_2", "name": "verify", "args": {"desc": "button"}}]},
            {"text_response": "Done", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = ["screenshot_data", "verified"]

        task_prompt = "Test"

        # Act
        specialist.execute_with_tools(task_prompt, basic_tools)

        # Assert: Third LLM call has full chain
        third_call = specialist.llm_adapter.invoke.call_args_list[2]
        request = third_call[0][0]
        messages = request.messages

        # Expected order: Human, AI(tool_call_1), Tool(result_1), AI(tool_call_2), Tool(result_2)
        assert len(messages) == 5
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert messages[1].tool_calls[0]["name"] == "screenshot"
        assert isinstance(messages[2], ToolMessage)
        assert messages[2].content == "screenshot_data"
        assert isinstance(messages[3], AIMessage)
        assert messages[3].tool_calls[0]["name"] == "verify"
        assert isinstance(messages[4], ToolMessage)
        assert messages[4].content == "verified"

    def test_error_result_formatted_correctly(self, specialist, basic_tools):
        """Test that error results are formatted with 'Error:' prefix."""
        # Arrange
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "click", "args": {}}]},
            {"text_response": "Handled error", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = Exception("Click failed")

        task_prompt = "Test"

        # Act
        specialist.execute_with_tools(task_prompt, basic_tools, stop_on_error=False)

        # Assert: Second LLM call should include error message
        second_call = specialist.llm_adapter.invoke.call_args_list[1]
        request = second_call[0][0]

        tool_messages = [m for m in request.messages if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert tool_messages[0].content.startswith("Error:")
        assert "Click failed" in tool_messages[0].content


# =============================================================================
# ReActMixin Tests - Serialize for Provider (ADR-CORE-055)
# =============================================================================

class TestSerializeForProvider:
    """Tests for _serialize_for_provider method (ADR-CORE-055)."""

    def test_empty_trace_produces_human_message_only(self, specialist):
        """Empty trace should produce just the goal as HumanMessage."""
        messages = specialist._serialize_for_provider(
            goal="Sort the files",
            trace=[]
        )

        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "Sort the files"

    def test_single_iteration_produces_three_messages(self, specialist):
        """One iteration should produce: Human, AI, Tool."""
        call = ToolCall(id="call_1", name="read_file", args={"path": "test.txt"})
        step = ReActIteration(
            iteration=0,
            tool_call=call,
            observation="file contents here",
            success=True
        )

        messages = specialist._serialize_for_provider(
            goal="Read the file",
            trace=[step]
        )

        assert len(messages) == 3
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert isinstance(messages[2], ToolMessage)

        # Verify AIMessage has tool_calls
        assert messages[1].tool_calls[0]["name"] == "read_file"
        assert messages[1].tool_calls[0]["id"] == "call_1"

        # Verify ToolMessage has result
        assert messages[2].content == "file contents here"
        assert messages[2].tool_call_id == "call_1"

    def test_multiple_iterations_preserve_order(self, specialist):
        """Multiple iterations maintain: Human, [AI, Tool]* pattern."""
        call1 = ToolCall(id="call_1", name="list_directory", args={"path": "."})
        call2 = ToolCall(id="call_2", name="read_file", args={"path": "a.txt"})
        call3 = ToolCall(id="call_3", name="move_file", args={"source": "a.txt", "destination": "b.txt"})

        trace = [
            ReActIteration(iteration=0, tool_call=call1, observation="[FILE] a.txt", success=True),
            ReActIteration(iteration=1, tool_call=call2, observation="apple", success=True),
            ReActIteration(iteration=2, tool_call=call3, observation="moved", success=True),
        ]

        messages = specialist._serialize_for_provider(
            goal="Sort files alphabetically",
            trace=trace
        )

        # Human + 3*(AI + Tool) = 7 messages
        assert len(messages) == 7
        assert isinstance(messages[0], HumanMessage)
        for i in range(3):
            assert isinstance(messages[1 + i*2], AIMessage)
            assert isinstance(messages[2 + i*2], ToolMessage)

    def test_concurrent_batch_groups_into_single_ai_message(self, specialist):
        """Concurrent calls (same iteration) should produce one AIMessage with multiple tool_calls."""
        call_a = ToolCall(id="call_0_0", name="read_file", args={"path": "a.txt"})
        call_b = ToolCall(id="call_0_1", name="read_file", args={"path": "b.txt"})
        call_c = ToolCall(id="call_0_2", name="read_file", args={"path": "c.txt"})

        trace = [
            ReActIteration(iteration=0, tool_call=call_a, observation="apple", success=True, thought="Read all three"),
            ReActIteration(iteration=0, tool_call=call_b, observation="banana", success=True, thought="Read all three"),
            ReActIteration(iteration=0, tool_call=call_c, observation="cherry", success=True, thought="Read all three"),
        ]

        messages = specialist._serialize_for_provider(goal="Read files", trace=trace)

        # Human + 1 AI (3 tool_calls) + 3 Tool = 5 messages
        assert len(messages) == 5
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert len(messages[1].tool_calls) == 3
        assert messages[1].tool_calls[0]["name"] == "read_file"
        assert messages[1].tool_calls[1]["id"] == "call_0_1"
        assert messages[1].tool_calls[2]["args"] == {"path": "c.txt"}
        assert isinstance(messages[2], ToolMessage)
        assert isinstance(messages[3], ToolMessage)
        assert isinstance(messages[4], ToolMessage)
        assert messages[2].content == "apple"
        assert messages[3].content == "banana"
        assert messages[4].content == "cherry"

    def test_mixed_single_and_concurrent_iterations(self, specialist):
        """Mix of single-call and concurrent-call iterations serializes correctly."""
        trace = [
            # Iteration 0: single call
            ReActIteration(
                iteration=0,
                tool_call=ToolCall(id="c0", name="list_directory", args={"path": "."}),
                observation="[FILE] a.txt\n[FILE] b.txt",
                success=True,
                thought="List first"
            ),
            # Iteration 1: concurrent batch (3 calls)
            ReActIteration(
                iteration=1,
                tool_call=ToolCall(id="c1_0", name="read_file", args={"path": "a.txt"}),
                observation="apple",
                success=True,
                thought="Read both"
            ),
            ReActIteration(
                iteration=1,
                tool_call=ToolCall(id="c1_1", name="read_file", args={"path": "b.txt"}),
                observation="banana",
                success=True,
                thought="Read both"
            ),
            ReActIteration(
                iteration=1,
                tool_call=ToolCall(id="c1_2", name="read_file", args={"path": "c.txt"}),
                observation="cherry",
                success=True,
                thought="Read both"
            ),
            # Iteration 2: single call
            ReActIteration(
                iteration=2,
                tool_call=ToolCall(id="c2", name="move_file", args={"source": "a.txt", "destination": "fruit/a.txt"}),
                observation="moved",
                success=True,
                thought="Move it"
            ),
        ]

        messages = specialist._serialize_for_provider(goal="Sort files", trace=trace)

        # Human + iter0(AI+Tool) + iter1(AI+3*Tool) + iter2(AI+Tool) = 1+2+4+2 = 9
        assert len(messages) == 9
        assert isinstance(messages[0], HumanMessage)

        # Iteration 0: single call
        assert isinstance(messages[1], AIMessage)
        assert len(messages[1].tool_calls) == 1
        assert messages[1].content == "List first"
        assert isinstance(messages[2], ToolMessage)

        # Iteration 1: concurrent batch
        assert isinstance(messages[3], AIMessage)
        assert len(messages[3].tool_calls) == 3
        assert messages[3].content == "Read both"
        assert isinstance(messages[4], ToolMessage)
        assert isinstance(messages[5], ToolMessage)
        assert isinstance(messages[6], ToolMessage)
        assert messages[4].tool_call_id == "c1_0"
        assert messages[5].tool_call_id == "c1_1"
        assert messages[6].tool_call_id == "c1_2"

        # Iteration 2: single call
        assert isinstance(messages[7], AIMessage)
        assert len(messages[7].tool_calls) == 1
        assert isinstance(messages[8], ToolMessage)

    def test_concurrent_batch_shared_thought_uses_first(self, specialist):
        """All entries in a batch share the same thought; serializer uses first entry's thought."""
        trace = [
            ReActIteration(
                iteration=0,
                tool_call=ToolCall(id="c0", name="read_file", args={"path": "a.txt"}),
                observation="apple", success=True, thought="I'll read both files"
            ),
            ReActIteration(
                iteration=0,
                tool_call=ToolCall(id="c1", name="read_file", args={"path": "b.txt"}),
                observation="banana", success=True, thought="I'll read both files"
            ),
        ]

        messages = specialist._serialize_for_provider(goal="Read", trace=trace)

        assert messages[1].content == "I'll read both files"
        assert len(messages[1].tool_calls) == 2


# =============================================================================
# Concurrent Multi-Tool-Call Dispatch Tests (#149)
# =============================================================================

class TestConcurrentDispatch:
    """Tests for concurrent dispatch when LLM returns multiple tool_calls."""

    def test_single_tool_call_dispatched_sequentially(self, specialist, basic_tools):
        """Single tool call should not use ThreadPoolExecutor."""
        specialist.llm_adapter.invoke.side_effect = [
            {"tool_calls": [{"id": "call_1", "name": "screenshot", "args": {}}]},
            {"text_response": "Done", "tool_calls": []}
        ]
        specialist.mcp_client.call.return_value = "screenshot_data"

        final_response, trace = specialist.execute_with_tools(
            task_prompt="Take a screenshot",
            tools=basic_tools,
            max_iterations=10
        )

        assert len(trace) == 1
        assert trace[0].tool_call.name == "screenshot"

    def test_multiple_tool_calls_dispatched_concurrently(self, specialist, basic_tools):
        """Multiple tool calls in one response should dispatch concurrently."""
        specialist.llm_adapter.invoke.side_effect = [
            {
                "tool_calls": [
                    {"id": "call_1", "name": "screenshot", "args": {}},
                    {"id": "call_2", "name": "verify", "args": {"description": "button"}},
                ]
            },
            {"text_response": "Both done", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = ["screenshot_data", True]

        final_response, trace = specialist.execute_with_tools(
            task_prompt="Screenshot and verify",
            tools=basic_tools,
            max_iterations=10
        )

        assert final_response == "Both done"
        assert len(trace) == 2
        assert trace[0].tool_call.name == "screenshot"
        assert trace[1].tool_call.name == "verify"
        # Both share the same iteration number (dispatched in same batch)
        assert trace[0].iteration == trace[1].iteration == 0

    def test_concurrent_dispatch_preserves_all_results(self, specialist, basic_tools):
        """All results from concurrent batch should appear in trace."""
        specialist.llm_adapter.invoke.side_effect = [
            {
                "tool_calls": [
                    {"id": "call_1", "name": "screenshot", "args": {}},
                    {"id": "call_2", "name": "verify", "args": {"description": "btn"}},
                    {"id": "call_3", "name": "click", "args": {"x": 10, "y": 20}},
                ]
            },
            {"text_response": "All three done", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = ["img", True, "clicked"]

        final_response, trace = specialist.execute_with_tools(
            task_prompt="Do three things",
            tools=basic_tools,
            max_iterations=10
        )

        assert len(trace) == 3
        assert all(t.success for t in trace)
        assert [t.tool_call.name for t in trace] == ["screenshot", "verify", "click"]

    def test_concurrent_dispatch_partial_failure(self, specialist, basic_tools):
        """Partial failures in concurrent batch are reported, not raised."""
        specialist.llm_adapter.invoke.side_effect = [
            {
                "tool_calls": [
                    {"id": "call_1", "name": "screenshot", "args": {}},
                    {"id": "call_2", "name": "click", "args": {"x": 10, "y": 20}},
                ]
            },
            {"text_response": "Handled partial failure", "tool_calls": []}
        ]
        # screenshot succeeds, click fails
        specialist.mcp_client.call.side_effect = ["img_data", Exception("Element not found")]

        final_response, trace = specialist.execute_with_tools(
            task_prompt="Screenshot and click",
            tools=basic_tools,
            max_iterations=10,
            stop_on_error=False,
        )

        assert len(trace) == 2
        assert trace[0].success is True
        assert trace[1].success is False
        assert "Element not found" in trace[1].observation

    def test_concurrent_batch_shares_thought(self, specialist, basic_tools):
        """All trace entries in a concurrent batch share the same thought."""
        specialist.llm_adapter.invoke.side_effect = [
            {
                "text_response": "I'll check both at once",
                "tool_calls": [
                    {"id": "call_1", "name": "screenshot", "args": {}},
                    {"id": "call_2", "name": "verify", "args": {"description": "btn"}},
                ]
            },
            {"text_response": "Done", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = ["img", True]

        _, trace = specialist.execute_with_tools(
            task_prompt="Check",
            tools=basic_tools,
            max_iterations=10
        )

        assert trace[0].thought == "I'll check both at once"
        assert trace[1].thought == "I'll check both at once"

    def test_concurrent_then_sequential_iterations(self, specialist, basic_tools):
        """Mix of concurrent and sequential calls across iterations."""
        specialist.llm_adapter.invoke.side_effect = [
            # Iteration 0: two concurrent calls
            {
                "tool_calls": [
                    {"id": "call_1", "name": "screenshot", "args": {}},
                    {"id": "call_2", "name": "verify", "args": {"description": "btn"}},
                ]
            },
            # Iteration 1: single sequential call
            {"tool_calls": [{"id": "call_3", "name": "click", "args": {"x": 5, "y": 5}}]},
            # Done
            {"text_response": "All done", "tool_calls": []}
        ]
        specialist.mcp_client.call.side_effect = ["img", True, "clicked"]

        final_response, trace = specialist.execute_with_tools(
            task_prompt="Full flow",
            tools=basic_tools,
            max_iterations=10
        )

        assert len(trace) == 3
        # First two share iteration 0
        assert trace[0].iteration == 0
        assert trace[1].iteration == 0
        # Third is iteration 1
        assert trace[2].iteration == 1
