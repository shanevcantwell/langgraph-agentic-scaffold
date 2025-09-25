# Audited on Sept 23, 2025
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.src.specialists.prompt_specialist import PromptSpecialist
from app.src.graph.state import GraphState
from app.src.utils.errors import LLMInvocationError


@pytest.fixture
def prompt_specialist(initialized_specialist_factory):
    """Fixture for an initialized PromptSpecialist."""
    return initialized_specialist_factory("PromptSpecialist")


def test_prompt_specialist_success(prompt_specialist):
    """Tests that the specialist correctly processes a response and updates the state."""
    # Arrange
    mock_adapter = prompt_specialist.llm_adapter
    mock_adapter.invoke.return_value = {"text_response": "This is the LLM response."}
    default_state = GraphState(messages=[HumanMessage(content="What should I do next?")])

    # Act
    result = prompt_specialist._execute_logic(default_state)

    # Assert
    mock_adapter.invoke.assert_called_once()
    assert isinstance(result["messages"][-1], AIMessage)
    assert "This is the LLM response." in result["messages"][-1].content


def test_prompt_specialist_handles_adapter_failure(prompt_specialist):
    """
    Tests that the specialist gracefully handles a connection or invocation error
    from the LLM adapter and populates the 'error' key in the state.
    """
    # Arrange
    mock_adapter = prompt_specialist.llm_adapter
    error_message = "Simulated connection failure to LLM provider."
    mock_adapter.invoke.side_effect = LLMInvocationError(error_message)
    default_state = GraphState(messages=[HumanMessage(content="What should I do next?")])

    # Act & Assert
    with pytest.raises(LLMInvocationError, match=error_message):
        prompt_specialist._execute_logic(default_state)


def test_prompt_specialist_handles_empty_messages(prompt_specialist):
    """Tests that the specialist does not call the LLM if there are no messages."""
    # Arrange
    empty_state = GraphState(messages=[])
    mock_adapter = prompt_specialist.llm_adapter

    # Act
    result = prompt_specialist._execute_logic(empty_state)

    # Assert
    mock_adapter.invoke.assert_not_called()
    assert len(result["messages"]) == 1
    assert "I have nothing to respond to" in result["messages"][0].content
