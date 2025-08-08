import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.router_specialist import RouterSpecialist
from src.graph.state import GraphState

@pytest.fixture
def specialist_and_state():
    """Provides a RouterSpecialist instance and a default state."""
    specialist = RouterSpecialist(llm_provider="gemini")
    state = GraphState(messages=[HumanMessage(content="Extract data for me")])
    return specialist, state

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_router_happy_path(mock_create_client, specialist_and_state):
    """Tests correct routing on valid LLM response."""
    specialist, state = specialist_and_state

    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='```json\n{"next_specialist": "data_extractor_specialist"}\n```')
    mock_create_client.return_value = mock_client

    result = specialist.execute(state)

    assert result["next_specialist"] == "data_extractor_specialist"

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_router_fallback_on_malformed_response(mock_create_client, specialist_and_state):
    """Tests fallback routing on non-JSON LLM response."""
    specialist, state = specialist_and_state

    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content="I am not sure what to do.")
    mock_create_client.return_value = mock_client

    result = specialist.execute(state)

    # Per the specialist's logic, it should fallback to the prompt_specialist
    assert result["next_specialist"] == "prompt_specialist"
