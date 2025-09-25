# Audit Date: Sept 23, 2025
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

    assert "extracted_data" in result_state
    assert result_state["extracted_data"] == {"name": "John Doe", "email": "john.doe@example.com"}
    assert result_state["artifacts"].get("text_to_process") is None # Artifact should be consumed
    assert isinstance(result_state["messages"][-1], AIMessage)
    assert "successfully extracted" in result_state["messages"][-1].content

def test_data_extractor_no_text_to_process(data_extractor_specialist):
    """
    Tests that the specialist handles missing input text gracefully by adding
    a message to the state instead of raising an error.
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Extract user info.")], "artifacts": {"text_to_process": None}}
 
    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)
 
    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_not_called()
    assert result_state.get("extracted_data") is None
    assert isinstance(result_state["messages"][-1], AIMessage)
    assert "'file_specialist' should probably run first" in result_state["messages"][-1].content

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

    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)

    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_not_called()
    assert "'file_specialist' should probably run first" in result_state["messages"][-1].content
    assert result_state.get("extracted_data") is None