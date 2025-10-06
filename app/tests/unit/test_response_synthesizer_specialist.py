# app/tests/unit/test_response_synthesizer_specialist.py
import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage

from app.src.specialists.response_synthesizer_specialist import ResponseSynthesizerSpecialist
from app.src.utils.errors import LLMInvocationError

@pytest.fixture
def response_synthesizer_specialist(initialized_specialist_factory):
    """Fixture for an initialized ResponseSynthesizerSpecialist."""
    return initialized_specialist_factory("ResponseSynthesizerSpecialist")

def test_synthesizer_with_snippets(response_synthesizer_specialist):
    """
    Tests that the synthesizer correctly processes snippets from the scratchpad,
    invokes the LLM, and returns the synthesized response as an artifact.
    """
    # Arrange
    mock_response = "This is the synthesized final response."
    response_synthesizer_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [],
        "scratchpad": {
            "user_response_snippets": ["Snippet 1.", "Snippet 2."]
        }
    }

    # Act
    result_state = response_synthesizer_specialist._execute_logic(initial_state)

    # Assert
    response_synthesizer_specialist.llm_adapter.invoke.assert_called_once()
    
    # Check that the final response is in artifacts
    assert "artifacts" in result_state
    assert result_state["artifacts"]["final_user_response.md"] == mock_response

    # Check that the snippets are cleared from the scratchpad
    assert "scratchpad" in result_state # This key should exist
    assert result_state["scratchpad"]["user_response_snippets"] == []

    # Check that a new AI message was created
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response

def test_synthesizer_without_snippets(response_synthesizer_specialist):
    """
    Tests that the synthesizer handles the case where no snippets are present
    and returns a default artifact without calling the LLM.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "scratchpad": {"user_response_snippets": []} # No snippets
    }

    # Act
    result_state = response_synthesizer_specialist._execute_logic(initial_state)

    # Assert
    response_synthesizer_specialist.llm_adapter.invoke.assert_not_called()
    assert "workflow has completed" in result_state["artifacts"]["final_user_response.md"]

@pytest.mark.parametrize("snippets", [
    [],
    ["", "   "]
], ids=["empty_list", "list_with_empty_strings"])
def test_synthesizer_with_empty_snippets_list(response_synthesizer_specialist, snippets):
    """
    Tests that the synthesizer handles an empty list of snippets or a list
    with only empty strings, returning a default artifact without calling the LLM.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "scratchpad": {"user_response_snippets": snippets}
    }

    # Act
    result_state = response_synthesizer_specialist._execute_logic(initial_state)

    # Assert
    response_synthesizer_specialist.llm_adapter.invoke.assert_not_called()
    assert "workflow has completed" in result_state["artifacts"]["final_user_response.md"]

def test_synthesizer_handles_llm_invocation_error(response_synthesizer_specialist):
    """Tests that an LLMInvocationError is caught and handled."""
    # Arrange
    response_synthesizer_specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API Error")
    initial_state = {
        "messages": [],
        "scratchpad": {"user_response_snippets": ["Some snippet."]}
    }

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API Error"):
        response_synthesizer_specialist._execute_logic(initial_state)

def test_synthesizer_handles_empty_llm_response(response_synthesizer_specialist):
    """Tests that an empty or None response from the LLM is handled gracefully."""
    # Arrange
    response_synthesizer_specialist.llm_adapter.invoke.return_value = {"text_response": None}
    initial_state = {
        "messages": [],
        "scratchpad": {"user_response_snippets": ["Some snippet."]}
    }

    # Act
    result_state = response_synthesizer_specialist._execute_logic(initial_state)

    # Assert
    response_synthesizer_specialist.llm_adapter.invoke.assert_called_once()
    assert "I was unable to generate a final response" in result_state["artifacts"]["final_user_response.md"]