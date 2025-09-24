# Audited on Sept 23, 2025
# app/tests/unit/test_text_analysis_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.text_analysis_specialist import TextAnalysisSpecialist
from app.src.utils.errors import LLMInvocationError

@pytest.fixture
def mock_llm_adapter():
    with patch('app.src.llm.factory.AdapterFactory.create_adapter') as mock_create_adapter:
        mock_adapter = MagicMock()
        mock_create_adapter.return_value = mock_adapter
        yield mock_adapter

@pytest.fixture
def specialist(mock_llm_adapter):
    """Fixture for an initialized TextAnalysisSpecialist with a mocked adapter."""
    s = TextAnalysisSpecialist("text_analysis_specialist", {"prompt_file": "fake.md"})
    s.llm_adapter = mock_llm_adapter
    return s

def test_text_analysis_with_text(specialist):
    """
    Tests the normal execution path where text is provided and successfully analyzed.
    """
    # Arrange
    mock_response = {"summary": "Test summary", "main_points": ["Point 1", "Point 2"]}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Analyze this.")],
        "text_to_process": "This is the text to analyze.",
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_called_once()
    assert "artifacts" in result_state
    assert result_state["artifacts"]["text_analysis"] == mock_response
    assert result_state["text_to_process"] is None  # Should be consumed
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Test summary" in result_state["messages"][0].content

def test_text_analysis_without_text_self_correction(specialist):
    """
    Tests the self-correction mechanism where no text is provided (is None).
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Analyze this.")], "text_to_process": None}

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called()  # LLM should not be called
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["file_specialist"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I cannot run because there is no text to process" in result_state["messages"][0].content

@pytest.mark.parametrize("text_input", ["", "   "], ids=["empty_string", "whitespace_only"])
def test_text_analysis_with_empty_text_input(specialist, text_input):
    """Tests self-correction when text_to_process is an empty or whitespace string."""
    # Arrange
    initial_state = {"messages": [], "text_to_process": text_input}

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called()
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["file_specialist"]

def test_text_analysis_handles_llm_invocation_error(specialist):
    """Tests that an LLMInvocationError is propagated correctly."""
    # Arrange
    specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": [], "text_to_process": "Some text."}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        specialist._execute_logic(initial_state)

def test_text_analysis_handles_malformed_llm_response(specialist):
    """Tests that the specialist raises an error if the LLM response is not valid JSON."""
    # Arrange
    specialist.llm_adapter.invoke.return_value = {"json_response": None}
    initial_state = {"messages": [], "text_to_process": "Some text."}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid JSON response"):
        specialist._execute_logic(initial_state)