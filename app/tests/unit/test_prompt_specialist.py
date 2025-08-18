import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage

from app.src.specialists.prompt_specialist import PromptSpecialist
from app.src.graph.state import GraphState
from app.src.llm.exceptions import LLMInvocationError

@pytest.fixture
def default_state():
    """Provides a default state for tests."""
    return GraphState(messages=[HumanMessage(content="What should I do next?")])

@patch('app.src.specialists.base.AdapterFactory.create_adapter')
def test_prompt_specialist_happy_path(mock_create_adapter, default_state):
    """Tests that the specialist correctly processes a response and updates the state."""
    mock_adapter = MagicMock()
    expected_response = AIMessage(content="This is the LLM response.")
    mock_adapter.invoke.return_value = expected_response
    mock_create_adapter.return_value = mock_adapter

    specialist = PromptSpecialist()
    result = specialist.execute(default_state)

    # The specialist should add the LLM's response to the message history
    assert isinstance(result["messages"][-1], AIMessage)
    assert result["messages"][-1] == expected_response
    assert "error" not in result

@patch('app.src.specialists.base.AdapterFactory.create_adapter')
def test_prompt_specialist_handles_adapter_failure(mock_create_adapter, default_state):
    """
    Tests that the specialist gracefully handles a connection or invocation error
    from the LLM adapter and populates the 'error' key in the state.
    """
    mock_adapter = MagicMock()
    error_message = "Simulated connection failure to LLM provider."
    mock_adapter.invoke.side_effect = LLMInvocationError(error_message)
    mock_create_adapter.return_value = mock_adapter

    specialist = PromptSpecialist()
    result = specialist.execute(default_state)

    assert "error" in result
    assert error_message in result["error"]
    assert "Failed to get a response from the LLM" in result["error"]
