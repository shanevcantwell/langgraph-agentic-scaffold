# app/tests/unit/test_response_synthesizer_specialist.py
import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage

from app.src.specialists.response_synthesizer_specialist import ResponseSynthesizerSpecialist

@pytest.fixture
def synthesizer_specialist():
    """Fixture for an initialized ResponseSynthesizerSpecialist."""
    specialist = ResponseSynthesizerSpecialist(
        specialist_name="response_synthesizer_specialist",
        specialist_config={"type": "llm"}
    )
    specialist.llm_adapter = MagicMock()
    return specialist

def test_synthesizer_with_snippets(synthesizer_specialist):
    """
    Tests that the synthesizer correctly processes snippets from the scratchpad,
    invokes the LLM, and returns the synthesized response as an artifact.
    """
    # Arrange
    mock_response = "This is the synthesized final response."
    synthesizer_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [],
        "scratchpad": {
            "user_response_snippets": ["Snippet 1.", "Snippet 2."]
        }
    }

    # Act
    result_state = synthesizer_specialist._execute_logic(initial_state)

    # Assert
    synthesizer_specialist.llm_adapter.invoke.assert_called_once()
    
    # Check that the final response is in artifacts
    assert "artifacts" in result_state
    assert result_state["artifacts"]["final_user_response.md"] == mock_response

    # Check that the snippets are cleared from the scratchpad
    assert "scratchpad" in result_state
    assert result_state["scratchpad"]["user_response_snippets"] == []

    # Check that a new AI message was created
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response

def test_synthesizer_without_snippets(synthesizer_specialist):
    """
    Tests that the synthesizer handles the case where no snippets are present
    and returns a default artifact without calling the LLM.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "scratchpad": {} # No snippets
    }

    # Act
    result_state = synthesizer_specialist._execute_logic(initial_state)

    # Assert
    synthesizer_specialist.llm_adapter.invoke.assert_not_called()
    assert "artifacts" in result_state
    assert "No specific user-facing response was synthesized." in result_state["artifacts"]["final_user_response.md"]
    assert "messages" not in result_state # No new message should be generated