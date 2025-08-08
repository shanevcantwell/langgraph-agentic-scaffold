import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.data_extractor_specialist import DataExtractorSpecialist
from src.graph.state import GraphState

@pytest.fixture
def specialist_and_state():
    """
    Provides a specialist instance and a default state, aligning with the
    class-based architecture defined in DEVELOPERS_GUIDE.md.
    """
    specialist = DataExtractorSpecialist(llm_provider="gemini")
    # The specialist expects the input text in the 'text_to_process' field of the state.
    state = GraphState(messages=[], text_to_process="Extract from: John Smith, john.s@work.com")
    return specialist, state

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_data_extractor_happy_path(mock_create_client, specialist_and_state):
    """Tests successful extraction and validation using the class-based specialist."""
    specialist, state = specialist_and_state
    
    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='```json\n{"name": "John Smith", "email": "john.s@work.com"}\n```')
    mock_create_client.return_value = mock_client

    result = specialist.execute(state)
    
    mock_client.invoke.assert_called_once()
    assert result["extracted_data"] == {"name": "John Smith", "email": "john.s@work.com"}

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_data_extractor_validation_error(mock_create_client, specialist_and_state):
    """Tests handling of data that fails Pydantic validation."""
    specialist, state = specialist_and_state
    
    mock_client = MagicMock()
    # Simulate the LLM returning data that is missing the required 'email' field.
    mock_client.invoke.return_value = AIMessage(content='```json\n{"name": "John Smith"}\n```')
    mock_create_client.return_value = mock_client

    result = specialist.execute(state)
    
    assert result["extracted_data"] is None
    # The specialist should return a dictionary containing an 'error' key on failure.
    assert "error" in result
    assert isinstance(result["error"], str)
