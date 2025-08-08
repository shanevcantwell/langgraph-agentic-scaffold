import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.data_extractor_specialist import data_extractor_specialist, Person
from src.state import AgentState

@pytest.fixture
def initial_state():
    """Provides a default state for the data extractor."""
    return AgentState(
        messages=[HumanMessage(content="Extract from: John Smith, john.s@work.com")],
        data_schema=Person
    )

def test_data_extractor_happy_path(mocker, initial_state):
    """Tests successful extraction and validation."""
    mock_response = AIMessage(content='```json\n{"name": "John Smith", "email": "john.s@work.com"}\n```')
    mocker.patch("langchain_google_genai.chat_models.ChatGoogleGenerativeAI.invoke", return_value=mock_response)

    result = data_extractor_specialist(initial_state)
    
    assert result["extracted_data"] == {"name": "John Smith", "email": "john.s@work.com"}

def test_data_extractor_validation_error(mocker, initial_state):
    """Tests handling of data that fails Pydantic validation."""
    mock_response = AIMessage(content='```json\n{"name": "John Smith"}\n```') # Missing email
    mocker.patch("langchain_google_genai.chat_models.ChatGoogleGenerativeAI.invoke", return_value=mock_response)

    result = data_extractor_specialist(initial_state)
    
    assert result["extracted_data"] is None
    assert "---DATA EXTRACTOR ERROR: Validation failed---" in result["messages"][-1].content
