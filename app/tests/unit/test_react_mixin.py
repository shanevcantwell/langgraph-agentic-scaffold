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
    ParallelCall,
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


# =============================================================================
# Parallel Tool Execution Tests
# =============================================================================

class TestParallelCallSchema:
    """Tests for ParallelCall schema and TOOL_PARAMETERS integration."""

    def test_parallel_call_creation(self):
        """Test basic ParallelCall model creation."""
        call = ParallelCall(tool="read_file", args={"path": "/test.txt"})
        assert call.tool == "read_file"
        assert call.args == {"path": "/test.txt"}

    def test_parallel_call_default_args(self):
        """Test ParallelCall with default empty args."""
        call = ParallelCall(tool="list_directory")
        assert call.args == {}

    def test_parallel_in_tool_parameters(self):
        """Verify 'parallel' is registered in TOOL_PARAMETERS."""
        assert "parallel" in ReActMixin.TOOL_PARAMETERS
        assert "calls" in ReActMixin.TOOL_PARAMETERS["parallel"]

    def test_build_tool_schemas_includes_parallel(self, specialist):
        """Verify _build_tool_schemas produces a valid schema for 'parallel'."""
        tools = {
            "read_file": ToolDef(service="filesystem", function="read_file", description="Read a file"),
            "parallel": ToolDef(service="system", function="parallel", description="Parallel exec"),
        }
        schemas = specialist._build_tool_schemas(tools)
        assert len(schemas) == 2

        # Find the parallel schema
        parallel_schema = next(s for s in schemas if s.__name__ == "parallel")
        json_schema = parallel_schema.model_json_schema()

        # Should have 'calls' property that references ParallelCall
        assert "calls" in json_schema.get("properties", {})


class TestParallelExecution:
    """Tests for _execute_parallel concurrent dispatch."""

    @pytest.fixture
    def parallel_tools(self):
        """Tools including parallel for testing."""
        return {
            "read_file": ToolDef(
                service="filesystem",
                function="read_file",
                description="Read a file"
            ),
            "search": ToolDef(
                service="web_specialist",
                function="search",
                description="Search the web"
            ),
            "parallel": ToolDef(
                service="system",
                function="parallel",
                description="Parallel execution"
            ),
        }

    def test_parallel_dispatches_concurrently(self, specialist, parallel_tools):
        """Test that parallel executes sub-calls and combines results."""
        # Mock _execute_tool for the sub-calls (bypass MCP)
        original_execute = specialist._execute_tool
        call_log = []

        def mock_execute(tool_call, tools, stop_on_error, successful_paths=None):
            if tool_call.name == "parallel":
                return original_execute(tool_call, tools, stop_on_error, successful_paths)
            call_log.append(tool_call.name)
            return ToolResult(
                call=tool_call,
                success=True,
                result=f"result_for_{tool_call.name}"
            )

        specialist._execute_tool = mock_execute

        parallel_call = ToolCall(
            id="call_p1",
            name="parallel",
            args={
                "calls": [
                    {"tool": "read_file", "args": {"path": "/a.txt"}},
                    {"tool": "read_file", "args": {"path": "/b.txt"}},
                    {"tool": "search", "args": {"query": "test"}},
                ]
            }
        )

        result = specialist._execute_parallel(parallel_call, parallel_tools, False)

        assert result.success is True
        assert len(call_log) == 3
        assert "result_for_read_file" in result.result
        assert "result_for_search" in result.result
        # All three sub-results should be in the combined output
        assert result.result.count("OK") == 3

    def test_parallel_partial_failure(self, specialist, parallel_tools):
        """Test that partial failures are reported, not raised."""
        original_execute = specialist._execute_tool

        def mock_execute(tool_call, tools, stop_on_error, successful_paths=None):
            if tool_call.name == "parallel":
                return original_execute(tool_call, tools, stop_on_error, successful_paths)
            if tool_call.name == "search":
                return ToolResult(call=tool_call, success=False, error="Network timeout")
            return ToolResult(call=tool_call, success=True, result="file contents")

        specialist._execute_tool = mock_execute

        parallel_call = ToolCall(
            id="call_p2",
            name="parallel",
            args={
                "calls": [
                    {"tool": "read_file", "args": {"path": "/a.txt"}},
                    {"tool": "search", "args": {"query": "test"}},
                ]
            }
        )

        result = specialist._execute_parallel(parallel_call, parallel_tools, False)

        # Overall success is False because one sub-call failed
        assert result.success is False
        # But both results are present in the observation
        assert "OK" in result.result
        assert "ERROR" in result.result
        assert "Network timeout" in result.result
        assert "file contents" in result.result

    def test_parallel_empty_calls_list(self, specialist, parallel_tools):
        """Test that empty calls list returns error."""
        parallel_call = ToolCall(
            id="call_empty",
            name="parallel",
            args={"calls": []}
        )

        result = specialist._execute_parallel(parallel_call, parallel_tools, False)

        assert result.success is False
        assert "empty calls list" in result.error

    def test_parallel_rejects_nested_parallel(self, specialist, parallel_tools):
        """Test that nested parallel calls are filtered out."""
        original_execute = specialist._execute_tool

        def mock_execute(tool_call, tools, stop_on_error, successful_paths=None):
            if tool_call.name == "parallel":
                return original_execute(tool_call, tools, stop_on_error, successful_paths)
            return ToolResult(call=tool_call, success=True, result="ok")

        specialist._execute_tool = mock_execute

        parallel_call = ToolCall(
            id="call_nested",
            name="parallel",
            args={
                "calls": [
                    {"tool": "read_file", "args": {"path": "/a.txt"}},
                    {"tool": "parallel", "args": {"calls": []}},  # Should be filtered
                ]
            }
        )

        result = specialist._execute_parallel(parallel_call, parallel_tools, False)

        # Only the read_file sub-call should have executed
        assert result.success is True
        assert result.result.count("read_file") == 1

    def test_parallel_all_nested_filtered_returns_error(self, specialist, parallel_tools):
        """Test that if all sub-calls are filtered, error is returned."""
        parallel_call = ToolCall(
            id="call_all_nested",
            name="parallel",
            args={
                "calls": [
                    {"tool": "parallel", "args": {"calls": []}},
                    {"tool": "parallel", "args": {"calls": []}},
                ]
            }
        )

        result = specialist._execute_parallel(parallel_call, parallel_tools, False)

        assert result.success is False
        assert "no valid sub-calls" in result.error

    def test_parallel_in_react_loop(self, specialist, parallel_tools):
        """Test parallel tool works end-to-end in the ReAct loop."""
        # Mock: LLM calls parallel, then returns final response
        specialist.llm_adapter.invoke.side_effect = [
            {
                "tool_calls": [{
                    "id": "call_p1",
                    "name": "parallel",
                    "args": {
                        "calls": [
                            {"tool": "read_file", "args": {"path": "/a.txt"}},
                            {"tool": "read_file", "args": {"path": "/b.txt"}},
                        ]
                    }
                }]
            },
            {
                "text_response": "Both files read successfully.",
                "tool_calls": []
            }
        ]

        # Mock external MCP for filesystem calls
        specialist.external_mcp_client = MagicMock()
        from app.src.mcp import extract_text_from_mcp_result

        # Create mock MCP results
        mock_result_a = MagicMock()
        mock_result_a.content = [MagicMock(text="contents of a")]
        mock_result_b = MagicMock()
        mock_result_b.content = [MagicMock(text="contents of b")]

        # sync_call_external_mcp will be called for each sub-call
        with patch('app.src.specialists.mixins.react_mixin.sync_call_external_mcp') as mock_mcp, \
             patch('app.src.specialists.mixins.react_mixin.extract_text_from_mcp_result') as mock_extract:
            mock_extract.side_effect = ["contents of a", "contents of b"]
            mock_mcp.return_value = mock_result_a  # Doesn't matter, extract is mocked

            final_response, trace = specialist.execute_with_tools(
                task_prompt="Read both files",
                tools=parallel_tools,
                max_iterations=10
            )

        assert final_response == "Both files read successfully."
        assert len(trace) == 1  # One parallel call = one trace entry
        assert trace[0].tool_call.name == "parallel"
        assert trace[0].success is True
        assert "contents of a" in trace[0].observation
        assert "contents of b" in trace[0].observation
