import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.data_extractor_specialist import DataExtractorSpecialist
from src.graph.state import GraphState

@pytest.fixture
def default_state():
    """
    Provides a default state for tests.
    """
    return GraphState(messages=[], text_to_process="Extract from: John Smith, john.s@work.com")

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_data_extractor_happy_path(mock_create_client, default_state):
    """Tests successful extraction and validation using the class-based specialist."""
    mock_client = MagicMock()
    mock_client.invoke.return_value = AIMessage(content='```json\n{"name": "John Smith", "email": "john.s@work.com"}\n```')
    mock_create_client.return_value = mock_client

    specialist = DataExtractorSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)
    
    mock_client.invoke.assert_called_once()
    assert result["extracted_data"] == {"name": "John Smith", "email": "john.s@work.com"}

@patch('src.llm.factory.LLMClientFactory.create_client')
def test_data_extractor_validation_error(mock_create_client, default_state):
    """Tests handling of data that fails Pydantic validation."""
    mock_client = MagicMock()
    # Simulate the LLM returning data that is missing the required 'email' field.
    mock_client.invoke.return_value = AIMessage(content='```json\n{"name": "John Smith"}\n```')
    mock_create_client.return_value = mock_client

    specialist = DataExtractorSpecialist(llm_provider="gemini")
    result = specialist.execute(default_state)
    
    # Assert that the email field is None when not provided, as per Optional[str]
    assert result["extracted_data"] == {"name": "John Smith", "email": None}
    # The specialist should NOT return an 'error' key for missing optional fields
    assert "error" not in result

