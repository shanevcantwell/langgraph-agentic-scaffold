# app/tests/unit/test_text_analysis_specialist.py
import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.text_analysis_specialist import TextAnalysisSpecialist
from app.src.utils.errors import LLMInvocationError
from app.src.utils.prompt_loader import load_prompt # Import load_prompt directly
from app.src.specialists.schemas import TextAnalysis


def _fake_call_tool_result(data: dict) -> MagicMock:
    """Wrap a dict as a fake MCP CallToolResult for testing the real parsing path."""
    text_content = MagicMock()
    text_content.text = json.dumps(data)
    result = MagicMock()
    result.content = [text_content]
    return result

@pytest.fixture
def text_analysis_specialist(initialized_specialist_factory):
    """Fixture for an initialized TextAnalysisSpecialist with a mocked adapter."""
    return initialized_specialist_factory("TextAnalysisSpecialist")

def test_text_analysis_with_text(text_analysis_specialist):
    """
    Tests the normal execution path where text is provided and successfully analyzed.
    """
    # Arrange
    mock_response = {"summary": "Test summary", "main_points": ["Point 1", "Point 2"]}
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Analyze this.")],
        "artifacts": {"text_to_process": "This is the text to analyze."},
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_called_once()
    called_request = text_analysis_specialist.llm_adapter.invoke.call_args[0][0]
    assert called_request.output_model_class == TextAnalysis

    assert "artifacts" in result_state
    # Results stored as list (supports 0→many invocations)
    results = result_state["artifacts"]["text_analysis_results"]
    assert len(results) == 1
    assert results[0]["data"] == mock_response
    assert results[0]["status"] == "complete"
    # Writes back to gathered_context for downstream visibility
    assert "gathered_context" in result_state["artifacts"]
    assert "Text Analysis" in result_state["artifacts"]["gathered_context"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Test summary" in result_state["messages"][0].content

def test_text_analysis_without_text_self_correction(text_analysis_specialist):
    """
    Tests graceful failure when no text is provided and no ReAct tools available.
    (Specialist has no external_mcp_client — not connected to prompt-prix in unit tests.)
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Analyze this.")], "artifacts": {"text_to_process": None}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "no text to process" in result_state["messages"][0].content
    # Should NOT signal completion — task wasn't done
    assert result_state.get("task_is_complete") is not True

@pytest.mark.parametrize("text_input", ["", "   "], ids=["empty_string", "whitespace_only"])
def test_text_analysis_with_empty_text_input(text_analysis_specialist, text_input):
    """Tests graceful failure when text_to_process is empty/whitespace and no ReAct tools."""
    # Arrange
    initial_state = {"messages": [], "artifacts": {"text_to_process": text_input}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "no text to process" in result_state["messages"][0].content

def test_text_analysis_handles_llm_invocation_error(text_analysis_specialist):
    """Tests that an LLMInvocationError is propagated correctly."""
    # Arrange
    text_analysis_specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": [], "artifacts": {"text_to_process": "Some text."}}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        text_analysis_specialist._execute_logic(initial_state)

def test_text_analysis_handles_malformed_llm_response(text_analysis_specialist):
    """Tests that the specialist raises an error if the LLM response is not valid JSON."""
    # Arrange
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": None}
    initial_state = {"messages": [], "artifacts": {"text_to_process": "Some text."}}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid JSON response"):
        text_analysis_specialist._execute_logic(initial_state)


# ==============================================================================
# Task Completion Signal Tests
# ==============================================================================

def test_text_analysis_does_not_claim_terminal_authority(text_analysis_specialist):
    """
    Test that TA does NOT set task_is_complete.

    Specialists are stateless functional primitives — termination is a graph-level
    decision owned by ExitInterview, not individual specialists. TA writes its
    results to gathered_context and artifacts, then yields control back to Router.
    """
    # Arrange
    mock_response = {"summary": "Analysis complete", "main_points": ["Point 1"]}
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Analyze this text.")],
        "artifacts": {"text_to_process": "Text to analyze."},
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert - TA should NOT set task_is_complete (that's EI's job)
    assert "task_is_complete" not in result_state


def test_text_analysis_no_task_complete_on_missing_text(text_analysis_specialist):
    """
    Test that task_is_complete is NOT set when text is missing.

    When text is missing and no ReAct tools are available, the specialist
    should NOT signal completion since the actual task hasn't been done yet.
    """
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Analyze this.")],
        "artifacts": {"text_to_process": None}
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert - task_is_complete should NOT be set at root level
    assert result_state.get("task_is_complete") is not True


# ==============================================================================
# Contextual Prompt Tests
# ==============================================================================

def test_text_analysis_treats_content_as_context(text_analysis_specialist):
    """
    Test that the specialist treats uploaded content as context, not target.

    Bug fixed: The specialist was appending "analyze this text" which caused
    the LLM to summarize the uploaded style guide instead of using it as
    a reference to analyze the chat snippet in the user's message.

    The fix changes the prompt to "this document has been provided as context"
    so the LLM follows the user's actual request.
    """
    # Arrange
    mock_response = {"summary": "Analysis based on context", "main_points": ["Point 1"]}
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    user_request = "Using this style guide, identify LLM tells in the following snippet: 'Delve into the tapestry...'"
    reference_doc = "Style Guide: Avoid words like 'delve', 'tapestry', etc."

    initial_state = {
        "messages": [HumanMessage(content=user_request)],
        "artifacts": {"text_to_process": reference_doc},
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert - verify the prompt treats content as context
    call_args = text_analysis_specialist.llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    # Find the appended context message
    context_message = None
    for msg in messages:
        if hasattr(msg, 'content') and "provided as context" in msg.content:
            context_message = msg
            break

    assert context_message is not None, "Should include 'provided as context' in prompt"
    assert "Perform the analysis requested by the user above" in context_message.content
    # Should NOT say "analyze this text" or similar directive that ignores user request
    assert "Please perform the requested analysis on the following text" not in context_message.content


def test_text_analysis_preserves_user_message(text_analysis_specialist):
    """
    Test that the user's original message is preserved in the context.

    The user's request (e.g., "use this reference to analyze X") should be
    visible to the LLM so it can follow the actual instruction.
    """
    # Arrange
    mock_response = {"summary": "Done", "main_points": []}
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    user_message = "Summarize the key takeaways from this document"
    initial_state = {
        "messages": [HumanMessage(content=user_message)],
        "artifacts": {"text_to_process": "Document content here."},
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert - user message should be in the messages sent to LLM
    call_args = text_analysis_specialist.llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    user_message_found = False
    for msg in messages:
        if hasattr(msg, 'content') and user_message in msg.content:
            user_message_found = True
            break

    assert user_message_found, "User's original message should be preserved in LLM context"


# ==============================================================================
# ReAct Path Tests (via prompt-prix MCP react_step)
# ==============================================================================

@pytest.fixture
def react_ta(text_analysis_specialist):
    """TA with mocked external_mcp_client simulating prompt-prix connectivity."""
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    text_analysis_specialist.external_mcp_client = mock_client
    text_analysis_specialist.llm_adapter.model_name = "test-model"
    text_analysis_specialist.llm_adapter.system_prompt = "You are a test specialist."
    return text_analysis_specialist


def test_react_path_completion(react_ta):
    """
    Test that the react_step path handles a simple completion (no tool calls).
    """
    # Arrange — react_step returns completed on first call
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp") as mock_mcp:
        mock_mcp.return_value = {
            "completed": True,
            "final_response": "The drift between the two texts is 0.28.",
            "new_iterations": [],
            "pending_tool_calls": [],
            "call_counter": 0,
            "latency_ms": 500.0,
        }

        initial_state = {
            "messages": [HumanMessage(content="Calculate drift between A and B.")],
            "artifacts": {"gathered_context": "Some facilitator context"},
        }

        # Act
        result = react_ta._execute_logic(initial_state)

    # Assert
    assert isinstance(result["messages"][0], AIMessage)
    assert "0.28" in result["messages"][0].content
    results = result["artifacts"]["text_analysis_results"]
    assert len(results) == 1
    assert results[0]["status"] == "complete"
    assert "gathered_context" in result["artifacts"]


def test_react_path_tool_dispatch(react_ta):
    """
    Test that pending tool calls from react_step are dispatched to real MCP services.
    """
    # Arrange — react_step returns pending tool call, then completes
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    call_count = 0

    def mock_mcp_side_effect(client, service, tool, args, **kwargs):
        nonlocal call_count
        call_count += 1
        if service == "prompt-prix" and tool == "react_step":
            if call_count == 1:
                # First call: model wants to calculate_drift
                return {
                    "completed": False,
                    "final_response": None,
                    "new_iterations": [],
                    "pending_tool_calls": [
                        {"id": "call_1", "name": "calculate_drift", "args": {"text_a": "hello", "text_b": "world"}},
                    ],
                    "call_counter": 1,
                    "thought": "I need to measure the drift.",
                    "latency_ms": 300.0,
                }
            else:
                # Second call: model completes
                return {
                    "completed": True,
                    "final_response": "The drift is 0.35.",
                    "new_iterations": [],
                    "pending_tool_calls": [],
                    "call_counter": 1,
                    "latency_ms": 200.0,
                }
        elif service == "semantic-chunker" and tool == "calculate_drift":
            # Real MCP tool dispatch — return a mock MCP result
            return "0.35"
        return "Error: unexpected call"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp", side_effect=mock_mcp_side_effect):
        with patch("app.src.specialists.text_analysis_specialist.extract_text_from_mcp_result", side_effect=lambda r: str(r)):
            initial_state = {
                "messages": [HumanMessage(content="Calculate drift.")],
                "artifacts": {"gathered_context": "Context from facilitator"},
            }

            # Act
            result = react_ta._execute_logic(initial_state)

    # Assert
    assert isinstance(result["messages"][0], AIMessage)
    assert "0.35" in result["messages"][0].content
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "complete"
    # Trace should contain the tool call
    assert len(results[0]["trace"]) == 1
    assert results[0]["trace"][0]["tool_call"]["name"] == "calculate_drift"
    assert results[0]["trace"][0]["success"] is True


def test_react_path_max_iterations(react_ta):
    """
    Test that the react_step path respects max_iterations.
    """
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"
    react_ta.specialist_config["max_iterations"] = 2

    def mock_mcp_always_pending(client, service, tool, args, **kwargs):
        if service == "prompt-prix":
            return {
                "completed": False,
                "final_response": None,
                "new_iterations": [],
                "pending_tool_calls": [
                    {"id": "call_1", "name": "read_file", "args": {"path": "/test"}},
                ],
                "call_counter": 1,
                "thought": "Reading...",
                "latency_ms": 100.0,
            }
        return "file contents here"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp", side_effect=mock_mcp_always_pending):
        with patch("app.src.specialists.text_analysis_specialist.extract_text_from_mcp_result", side_effect=lambda r: str(r)):
            initial_state = {
                "messages": [HumanMessage(content="Read and analyze.")],
                "artifacts": {"gathered_context": "Context"},
            }

            result = react_ta._execute_logic(initial_state)

    # Assert — should hit max_iterations and return partial
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "max_iterations"
    assert "iteration limit" in result["messages"][0].content


def test_react_path_mcp_error(react_ta):
    """
    Test graceful handling when react_step MCP call fails.
    """
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp", side_effect=RuntimeError("MCP timeout")):
        initial_state = {
            "messages": [HumanMessage(content="Analyze something.")],
            "artifacts": {"gathered_context": "Context"},
        }

        result = react_ta._execute_logic(initial_state)

    # Assert — should return error result, not crash
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "error"
    assert "MCP timeout" in result["messages"][0].content


def test_react_path_unknown_tool(react_ta):
    """
    Test that unknown tool names in pending calls are handled gracefully.
    """
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    call_count = 0

    def mock_mcp(client, service, tool, args, **kwargs):
        nonlocal call_count
        call_count += 1
        if service == "prompt-prix" and call_count == 1:
            return {
                "completed": False,
                "final_response": None,
                "new_iterations": [],
                "pending_tool_calls": [
                    {"id": "call_1", "name": "nonexistent_tool", "args": {}},
                ],
                "call_counter": 1,
                "thought": "Trying something.",
                "latency_ms": 100.0,
            }
        elif service == "prompt-prix":
            return {
                "completed": True,
                "final_response": "Done despite error.",
                "new_iterations": [],
                "pending_tool_calls": [],
                "call_counter": 1,
                "latency_ms": 100.0,
            }
        return "Error: unexpected"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp", side_effect=mock_mcp):
        initial_state = {
            "messages": [HumanMessage(content="Try something.")],
            "artifacts": {"gathered_context": "Context"},
        }

        result = react_ta._execute_logic(initial_state)

    # Assert — should handle gracefully (error observation fed back)
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "complete"
    trace = results[0]["trace"]
    assert trace[0]["success"] is False
    assert "Unknown tool" in trace[0]["observation"]


def test_react_capability_detection(text_analysis_specialist):
    """
    Test that _has_react_capability correctly detects prompt-prix connectivity.
    """
    # No external_mcp_client → no react
    assert text_analysis_specialist._has_react_capability() is False

    # Client exists but prompt-prix not connected
    mock_client = MagicMock()
    mock_client.is_connected.return_value = False
    text_analysis_specialist.external_mcp_client = mock_client
    assert text_analysis_specialist._has_react_capability() is False

    # Client exists and prompt-prix connected
    mock_client.is_connected.side_effect = lambda s: s == "prompt-prix"
    assert text_analysis_specialist._has_react_capability() is True


def test_openai_tool_schema_format(text_analysis_specialist):
    """
    Test that _build_openai_tool_schemas produces valid OpenAI function calling format.
    """
    tools = text_analysis_specialist._build_tools()
    schemas = text_analysis_specialist._build_openai_tool_schemas(tools)

    assert len(schemas) == len(tools)
    for schema in schemas:
        assert schema["type"] == "function"
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]
        assert schema["function"]["parameters"]["type"] == "object"

    # Verify specific tool has correct params
    drift_schema = next(s for s in schemas if s["function"]["name"] == "calculate_drift")
    assert "text_a" in drift_schema["function"]["parameters"]["properties"]
    assert "text_b" in drift_schema["function"]["parameters"]["properties"]


# ==============================================================================
# CallToolResult Parsing Tests (production MCP path)
# ==============================================================================

def test_parse_react_step_result_from_call_tool_result(react_ta):
    """
    Test that _parse_react_step_result correctly handles real MCP CallToolResult objects.

    In production, sync_call_external_mcp returns a CallToolResult with
    .content[0].text containing JSON. This test ensures the extraction + parsing
    pipeline works end-to-end.

    Bug fixed: 'CallToolResult' object has no attribute 'get' — TA was treating
    the raw MCP result as a dict instead of extracting text and parsing JSON.
    """
    data = {
        "completed": True,
        "final_response": "Drift is 0.28",
        "pending_tool_calls": [],
        "call_counter": 0,
        "latency_ms": 150.0,
    }
    fake_result = _fake_call_tool_result(data)
    parsed = react_ta._parse_react_step_result(fake_result)

    assert isinstance(parsed, dict)
    assert parsed["completed"] is True
    assert parsed["final_response"] == "Drift is 0.28"


def test_parse_react_step_result_dict_passthrough(react_ta):
    """Test that dicts pass through _parse_react_step_result unchanged."""
    data = {"completed": True, "final_response": "Done"}
    assert react_ta._parse_react_step_result(data) == data


def test_parse_react_step_result_permission_denied(react_ta):
    """Test that string (permission denied) passes through as-is."""
    error = "Permission Denied: Service 'prompt-prix' is not available"
    assert react_ta._parse_react_step_result(error) == error


def test_react_path_with_call_tool_result(react_ta):
    """
    End-to-end test: react_step returns a CallToolResult (like production),
    TA parses it and produces a proper message + artifacts.

    This is the regression test for the 'CallToolResult has no attribute get' crash.
    """
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp") as mock_mcp:
        mock_mcp.return_value = _fake_call_tool_result({
            "completed": True,
            "final_response": "The semantic drift between the strings is 0.31.",
            "new_iterations": [],
            "pending_tool_calls": [],
            "call_counter": 0,
            "latency_ms": 250.0,
        })

        initial_state = {
            "messages": [HumanMessage(content="Calculate drift between A and B.")],
            "artifacts": {"gathered_context": "Facilitator context"},
        }

        result = react_ta._execute_logic(initial_state)

    # Assert — proper message and artifacts produced
    assert isinstance(result["messages"][0], AIMessage)
    assert "0.31" in result["messages"][0].content
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "complete"
    assert "gathered_context" in result["artifacts"]


def test_react_error_produces_message_and_artifacts(react_ta):
    """
    Test that errors in the react loop produce a message and artifacts,
    NOT just a silent scratchpad entry.

    Bug fixed: when an exception occurred after the MCP call (e.g., parsing
    the result), it propagated to SafeExecutor which wrote to scratchpad only.
    The widened try/except now catches all loop errors and produces
    _build_error_result with a proper message and artifacts.
    """
    react_ta.external_mcp_client.is_connected.side_effect = lambda s: s == "prompt-prix"

    with patch("app.src.specialists.text_analysis_specialist.sync_call_external_mcp") as mock_mcp:
        # Return something that will cause an error during processing
        mock_mcp.return_value = None  # extract_text_from_mcp_result(None) → ""

        initial_state = {
            "messages": [HumanMessage(content="Analyze something.")],
            "artifacts": {"gathered_context": "Context"},
        }

        result = react_ta._execute_logic(initial_state)

    # Assert — error produces a MESSAGE (visible in conversation)
    assert "messages" in result
    assert isinstance(result["messages"][0], AIMessage)
    # Assert — error produces ARTIFACTS (visible in archive)
    assert "artifacts" in result
    results = result["artifacts"]["text_analysis_results"]
    assert results[0]["status"] == "error"
