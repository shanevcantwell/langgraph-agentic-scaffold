# Audited on Sept 23, 2025
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.src.specialists.prompt_specialist import PromptSpecialist
from app.src.graph.state import GraphState
from app.src.utils.errors import LLMInvocationError

@pytest.fixture
def default_state():
    """Provides a default state for tests."""
    return GraphState(messages=[HumanMessage(content="What should I do next?")])

@pytest.fixture
def prompt_specialist(initialized_specialist_factory):
    """Creates a PromptSpecialist instance using the factory fixture."""
    return initialized_specialist_factory("PromptSpecialist")

def test_prompt_specialist_success(prompt_specialist, default_state):
    """Tests that the specialist correctly processes a response and updates the state."""
    # Arrange
    mock_adapter = prompt_specialist.llm_adapter
    expected_response = AIMessage(content="This is the LLM response.")
    mock_adapter.invoke.return_value = expected_response

    # Act
    result = prompt_specialist.execute(default_state)

    # Assert
    mock_adapter.invoke.assert_called_once()
    # The specialist should add the LLM's response to the message history
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1] == expected_response
    assert "error" not in result

def test_prompt_specialist_handles_adapter_failure(prompt_specialist, default_state):
    """
    Tests that the specialist gracefully handles a connection or invocation error
    from the LLM adapter and populates the 'error' key in the state.
    """
    # Arrange
    mock_adapter = prompt_specialist.llm_adapter
    error_message = "Simulated connection failure to LLM provider."
    mock_adapter.invoke.side_effect = LLMInvocationError(error_message)

    # Act
    result = prompt_specialist.execute(default_state)

    # Assert
    assert "error" in result
    assert error_message in result["error"]
    assert "Failed to get a response from the LLM" in result["error"]

def test_prompt_specialist_handles_empty_messages(prompt_specialist):
    """Tests that the specialist does not call the LLM if there are no messages."""
    # Arrange
    empty_state = GraphState(messages=[])
    mock_adapter = prompt_specialist.llm_adapter

    # Act
    result = prompt_specialist.execute(empty_state)

    # Assert
    mock_adapter.invoke.assert_not_called()
    assert "error" not in result
    assert len(result["messages"]) == 0 # No new messages should be added

def test_prompt_specialist_initialization(prompt_specialist):
    """Tests that the specialist can be initialized without errors."""
    # This is a simple smoke test to ensure the constructor and its
    # dependencies (like loading prompts or configs) don't immediately fail.
    assert prompt_specialist is not None
    assert prompt_specialist.specialist_name == "prompt_specialist"
    assert hasattr(prompt_specialist, "llm_adapter")
