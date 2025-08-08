import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import PromptSpecialist
from src.graph.state import GraphState

@pytest.fixture
def specialist_and_state():
    """Provides a PromptSpecialist instance and a default state."""
    specialist = PromptSpecialist(llm_provider="gemini")
    state = GraphState(messages=[HumanMessage(content="What should I do next?")])
    return specialist, state

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_prompt_specialist_happy_path(mock_create_client, specialist_and_state):
    """Tests that the specialist correctly processes a response and updates the state."""
    specialist, state = specialist_and_state

    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='{"response": "You should ask the file specialist to list files."}')
    mock_create_client.return_value = mock_client

    result = specialist.execute(state)

    # The specialist should add the LLM's response to the message history
    assert "You should ask the file specialist to list files." in result["messages"][-1].content
    assert isinstance(result["messages"][-1], AIMessage)