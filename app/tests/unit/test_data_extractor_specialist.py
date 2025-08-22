import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists.data_extractor_specialist import DataExtractorSpecialist
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# Common fixtures for mocking specialist dependencies
@pytest.fixture
def mock_config_loader():
    with patch('app.src.specialists.base.ConfigLoader') as mock_loader:
        mock_loader.return_value.get_specialist_config.return_value = {"prompt_file": "fake.md"}
        mock_loader.return_value.get_provider_config.return_value = {}
        yield mock_loader

@pytest.fixture
def mock_adapter_factory():
    with patch('app.src.specialists.base.AdapterFactory') as mock_factory:
        mock_adapter = MagicMock()
        mock_factory.return_value.create_adapter.return_value = mock_adapter
        yield mock_factory, mock_adapter

@pytest.fixture
def mock_load_prompt():
    with patch('app.src.specialists.base.load_prompt') as mock_load:
        mock_load.return_value = "Fake system prompt"
        yield mock_load

@pytest.fixture
def data_extractor_specialist(mock_config_loader, mock_adapter_factory, mock_load_prompt):
    specialist = DataExtractorSpecialist(specialist_name="data_extractor_specialist")
    specialist.llm_adapter = mock_adapter_factory[1]
    return specialist

# Test cases
def test_data_extractor_success(data_extractor_specialist):
    """Tests successful data extraction and state update."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info from the text.")],
        "text_to_process": "User name is John Doe, email is john.doe@example.com"
    }
    mock_json_response = {"extracted_json": {"name": "John Doe", "email": "john.doe@example.com"}}
    data_extractor_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}

    # Act
    result_state = data_extractor_specialist._execute_logic(initial_state)

    # Assert
    data_extractor_specialist.llm_adapter.invoke.assert_called_once()
    # Check that a SystemMessage with the text to process was added for the LLM call
    call_args, _ = data_extractor_specialist.llm_adapter.invoke.call_args
    llm_messages = call_args[0].messages
    assert any("John Doe" in msg.content for msg in llm_messages if isinstance(msg, SystemMessage))

    assert "extracted_data" in result_state
    assert result_state["extracted_data"] == {"name": "John Doe", "email": "john.doe@example.com"}
    assert result_state["text_to_process"] is None # Artifact should be consumed
    assert isinstance(result_state["messages"][-1], AIMessage)
    assert "successfully extracted" in result_state["messages"][-1].content

def test_data_extractor_no_text_to_process(data_extractor_specialist):
    """Tests that the specialist raises an error if no text is provided."""
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Extract user info.")], "text_to_process": None}

    # Act & Assert
    with pytest.raises(ValueError, match="Input text not found"):
        data_extractor_specialist._execute_logic(initial_state)

def test_data_extractor_llm_fails(data_extractor_specialist):
    """Tests that the specialist raises an error if the LLM returns no JSON."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info.")],
        "text_to_process": "Some text here"
    }
    data_extractor_specialist.llm_adapter.invoke.return_value = {"json_response": None}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid JSON response"):
        data_extractor_specialist._execute_logic(initial_state)