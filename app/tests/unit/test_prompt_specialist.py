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

@patch('app.src.llm.factory.AdapterFactory.create_adapter')
def test_prompt_specialist_success(mock_create_adapter, default_state):
    """Tests that the specialist correctly processes a response and updates the state."""
    mock_adapter = MagicMock()
    expected_response = AIMessage(content="This is the LLM response.")
    mock_adapter.invoke.return_value = expected_response
    mock_create_adapter.return_value = mock_adapter

    specialist = PromptSpecialist(specialist_name="prompt_specialist", specialist_config={})
    result = specialist.execute(default_state)

    # The specialist should add the LLM's response to the message history
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1] == expected_response
    assert "error" not in result

@patch('app.src.llm.factory.AdapterFactory.create_adapter')
def test_prompt_specialist_handles_adapter_failure(mock_create_adapter, default_state):
    """
    Tests that the specialist gracefully handles a connection or invocation error
    from the LLM adapter and populates the 'error' key in the state.
    """
    mock_adapter = MagicMock()
    error_message = "Simulated connection failure to LLM provider."
    mock_adapter.invoke.side_effect = LLMInvocationError(error_message)
    mock_create_adapter.return_value = mock_adapter

    specialist = PromptSpecialist(specialist_name="prompt_specialist", specialist_config={})
    result = specialist.execute(default_state)

    assert "error" in result
    assert error_message in result["error"]
    assert "Failed to get a response from the LLM" in result["error"]

@patch('app.src.llm.factory.AdapterFactory.create_adapter')
def test_prompt_specialist_handles_empty_messages(mock_create_adapter):
    """Tests that the specialist does not call the LLM if there are no messages."""
    # Arrange
    empty_state = GraphState(messages=[])
    mock_adapter = MagicMock()
    mock_create_adapter.return_value = mock_adapter

    specialist = PromptSpecialist(specialist_name="prompt_specialist", specialist_config={})

    # Act
    result = specialist.execute(empty_state)

    # Assert
    mock_adapter.invoke.assert_not_called()
    assert "error" not in result
    assert len(result["messages"]) == 0 # No new messages should be added

@patch('app.src.llm.factory.AdapterFactory.create_adapter')
def test_prompt_specialist_handles_adapter_creation_failure(mock_create_adapter, default_state):
    """Tests that an error is handled if the AdapterFactory fails."""
    # Arrange
    error_message = "Could not create adapter for specialist."
    mock_create_adapter.side_effect = Exception(error_message)

    specialist = PromptSpecialist(specialist_name="prompt_specialist", specialist_config={})

    # Act
    result = specialist.execute(default_state)

    # Assert
    assert "error" in result
    assert "Failed to initialize LLM adapter" in result["error"]
    assert error_message in result["error"]

def test_prompt_specialist_initialization():
    """Tests that the specialist can be initialized without errors."""
    # This is a simple smoke test to ensure the constructor and its
    # dependencies (like loading prompts or configs) don't immediately fail.
    with patch('app.src.utils.prompt_loader.load_prompt'), patch('app.src.utils.config_loader.ConfigLoader'):
        specialist = PromptSpecialist(specialist_name="prompt_specialist", specialist_config={})
        assert specialist is not None
