
import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists.data_extractor_specialist import DataExtractorSpecialist
from app.src.utils.errors import LLMInvocationError
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

@pytest.fixture
def data_extractor_specialist(initialized_specialist_factory):
    """Fixture for an initialized DataExtractorSpecialist."""
    return initialized_specialist_factory("DataExtractorSpecialist")

# Test cases
def test_data_extractor_success(data_extractor_specialist):
    """Tests successful data extraction and state update."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info from the text.")],
        "artifacts": {"text_to_process": "User name is John Doe, email is john.doe@example.com"}
    }
    mock_json_response = {"extracted_json": {"name": "John Doe", "email": "john.doe@example.com"}}
    data_extractor_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}

    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)

    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_called_once()
    # Check that a SystemMessage with the text to process was added for the LLM call
    call_args, _ = data_extractor_specialist.llm_adapter.invoke.call_args
    llm_messages = call_args[0].messages
    assert any("John Doe" in msg.content for msg in llm_messages if isinstance(msg, HumanMessage))

    assert "extracted_data" in result_state["artifacts"]
    assert result_state["artifacts"]["extracted_data"] == {"name": "John Doe", "email": "john.doe@example.com"}
    assert result_state.get("text_to_process") is None # Artifact should be consumed
    assert isinstance(result_state["messages"][-1], AIMessage)
    assert "successfully extracted" in result_state["messages"][-1].content

def test_data_extractor_fallback_to_message_content(data_extractor_specialist):
    """
    Tests that the specialist uses message content when artifact is missing.
    This is the fallback behavior per Issue #8.
    """
    # Arrange - no artifact, but message has extractable content
    initial_state = {
        "messages": [HumanMessage(content="User name is Jane, email jane@test.com")],
        "artifacts": {"text_to_process": None}
    }
    mock_json_response = {"extracted_json": {"name": "Jane", "email": "jane@test.com"}}
    data_extractor_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}

    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)

    # Assert - LLM should be called with the message content
    data_extractor_specialist.llm_adapter.invoke.assert_called_once()
    assert "extracted_data" in result_state["artifacts"]
    assert result_state["artifacts"]["extracted_data"] == {"name": "Jane", "email": "jane@test.com"}


def test_data_extractor_no_text_anywhere(data_extractor_specialist):
    """
    Tests that the specialist handles truly empty input gracefully when both
    artifact and message content are empty/missing.
    """
    # Arrange - empty message content and no artifact
    initial_state = {
        "messages": [HumanMessage(content="   ")],  # whitespace only
        "artifacts": {"text_to_process": None}
    }

    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)

    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_not_called()
    assert result_state.get("artifacts", {}).get("extracted_data") is None
    assert isinstance(result_state["messages"][-1], AIMessage)
    assert "no text was provided" in result_state["messages"][-1].content

def test_data_extractor_llm_fails(data_extractor_specialist):
    """Tests that the specialist raises an error if the LLM returns no valid JSON payload."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info.")],
        "artifacts": {"text_to_process": "Some text here"}
    }
    data_extractor_specialist.llm_adapter.invoke.return_value = {"json_response": None}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid JSON response"):
        data_extractor_specialist._execute_logic(initial_state)

def test_data_extractor_handles_llm_invocation_error(data_extractor_specialist):
    """Tests that the specialist propagates LLM invocation errors."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info.")],
        "artifacts": {"text_to_process": "Some text here"}
    }
    data_extractor_specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API connection failed")

    # Act & Assert
    # The error should be propagated up to be caught by the graph's safe executor
    with pytest.raises(LLMInvocationError, match="API connection failed"):
        data_extractor_specialist._execute_logic(initial_state)

@pytest.mark.skip(reason="Assertion expects old behavior. See Issue #13: https://github.com/shanevcantwell/langgraph-agentic-scaffold/issues/13")
@pytest.mark.parametrize("text_input", [
    "",
    "   "
], ids=["empty_string", "whitespace_only"])
def test_data_extractor_no_text_to_process_on_empty_string(data_extractor_specialist, text_input):
    """
    Tests that the specialist self-corrects if the input text is empty or just whitespace.
    """
    # Arrange
    initial_state = {"messages": [], "artifacts": {"text_to_process": text_input}}
    result_state = data_extractor_specialist._execute_logic(initial_state)
    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_not_called()
    assert "'file_specialist' should probably run first" in result_state["messages"][-1].content