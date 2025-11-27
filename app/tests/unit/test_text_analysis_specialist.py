# app/tests/unit/test_text_analysis_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.text_analysis_specialist import TextAnalysisSpecialist
from app.src.utils.errors import LLMInvocationError
from app.src.utils.prompt_loader import load_prompt # Import load_prompt directly
from app.src.specialists.schemas import TextAnalysis

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
    assert result_state["artifacts"]["text_analysis"] == mock_response
    assert "text_analysis_report.md" in result_state["artifacts"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Test summary" in result_state["messages"][0].content

def test_text_analysis_without_text_self_correction(text_analysis_specialist):
    """
    Tests the self-correction mechanism where no text is provided (is None).
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Analyze this.")], "artifacts": {"text_to_process": None}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()  # LLM should not be called
    # Task 2.7: recommended_specialists moved to scratchpad
    assert "scratchpad" in result_state and "recommended_specialists" in result_state["scratchpad"]
    assert result_state["scratchpad"]["recommended_specialists"] == ["file_specialist"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I cannot run because there is no text to process" in result_state["messages"][0].content

@pytest.mark.parametrize("text_input", ["", "   "], ids=["empty_string", "whitespace_only"])
def test_text_analysis_with_empty_text_input(text_analysis_specialist, text_input):
    """Tests self-correction when text_to_process is an empty or whitespace string."""
    # Arrange
    initial_state = {"messages": [], "artifacts": {"text_to_process": text_input}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()
    # Task 2.7: recommended_specialists moved to scratchpad
    assert "scratchpad" in result_state and "recommended_specialists" in result_state["scratchpad"]
    assert result_state["scratchpad"]["recommended_specialists"] == ["file_specialist"]

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

def test_text_analysis_sets_task_is_complete(text_analysis_specialist):
    """
    Test that successful analysis sets task_is_complete at root level.

    Bug fixed: Without task_is_complete=True at ROOT level (not scratchpad),
    check_task_completion() wouldn't see it, causing Router to keep routing
    back to text_analysis_specialist until loop detection kicked in.
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

    # Assert - verify task_is_complete is set at ROOT level (not scratchpad!)
    # check_task_completion() checks state.get("task_is_complete"), not scratchpad
    assert result_state.get("task_is_complete") is True


def test_text_analysis_no_task_complete_on_missing_text(text_analysis_specialist):
    """
    Test that task_is_complete is NOT set when text is missing (self-correction path).

    When text is missing, the specialist recommends file_specialist and should
    NOT signal completion since the actual task hasn't been done yet.
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