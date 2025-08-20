import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.router_specialist import RouterSpecialist
from src.graph.state import GraphState

@pytest.fixture
def default_state():
    """Provides a default state for tests."""
    return GraphState(messages=[HumanMessage(content="Extract data for me")])

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_router_happy_path(mock_create_client, default_state):
    """Tests correct routing on valid LLM response."""
    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='```json\n{"next_specialist": "data_extractor_specialist"}\n```')
    mock_create_client.return_value = mock_client

    specialist = RouterSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)

    assert result["next_specialist"] == "data_extractor_specialist"

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_router_fallback_on_malformed_response(mock_create_client, default_state):
    """Tests fallback routing on non-JSON LLM response."""
    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content="I am not sure what to do.")
    mock_create_client.return_value = mock_client

    specialist = RouterSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)

    # Per the specialist's logic, it should fallback to the prompt_specialist
    assert result["next_specialist"] == "prompt_specialist"

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_router_fallback_on_unknown_specialist(mock_create_client, default_state):
    """Tests fallback routing on an unknown specialist name."""
    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='```json\n{"next_specialist": "unknown_specialist"}\n```')
    mock_create_client.return_value = mock_client

    specialist = RouterSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)

    # Per the specialist's logic, it should fallback to the prompt_specialist
    assert result["next_specialist"] == "prompt_specialist"