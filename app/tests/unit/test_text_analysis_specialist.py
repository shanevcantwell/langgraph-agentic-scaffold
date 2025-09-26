# app/tests/unit/test_text_analysis_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.text_analysis_specialist import TextAnalysisSpecialist
from app.src.utils.errors import LLMInvocationError
from app.src.utils.prompt_loader import load_prompt # Import load_prompt directly
from app.src.specialists.schemas import TextAnalysis

@pytest.fixture
def text_analysis_specialist(initialized_specialist_factory):
    """Fixture for an initialized TextAnalysisSpecialist with a mocked adapter."""
    return initialized_specialist_factory("TextAnalysisSpecialist")

def test_text_analysis_with_text(text_analysis_specialist):
    """
    Tests the normal execution path where text is provided and successfully analyzed.
    """
    # Arrange
    mock_response = {"summary": "Test summary", "main_points": ["Point 1", "Point 2"]}
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Analyze this.")],
        "artifacts": {"text_to_process": "This is the text to analyze."},
    }

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_called_once()
    called_request = text_analysis_specialist.llm_adapter.invoke.call_args[0][0]
    assert called_request.output_model_class == TextAnalysis

    assert "artifacts" in result_state
    assert result_state["artifacts"]["text_analysis"] == mock_response
    assert "text_analysis_report.md" in result_state["artifacts"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Test summary" in result_state["messages"][0].content

def test_text_analysis_without_text_self_correction(text_analysis_specialist):
    """
    Tests the self-correction mechanism where no text is provided (is None).
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Analyze this.")], "artifacts": {"text_to_process": None}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()  # LLM should not be called
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["file_specialist"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I cannot run because there is no text to process" in result_state["messages"][0].content

@pytest.mark.parametrize("text_input", ["", "   "], ids=["empty_string", "whitespace_only"])
def test_text_analysis_with_empty_text_input(text_analysis_specialist, text_input):
    """Tests self-correction when text_to_process is an empty or whitespace string."""
    # Arrange
    initial_state = {"messages": [], "artifacts": {"text_to_process": text_input}}

    # Act
    result_state = text_analysis_specialist._execute_logic(initial_state)

    # Assert
    text_analysis_specialist.llm_adapter.invoke.assert_not_called()
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["file_specialist"]

def test_text_analysis_handles_llm_invocation_error(text_analysis_specialist):
    """Tests that an LLMInvocationError is propagated correctly."""
    # Arrange
    text_analysis_specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": [], "artifacts": {"text_to_process": "Some text."}}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        text_analysis_specialist._execute_logic(initial_state)

def test_text_analysis_handles_malformed_llm_response(text_analysis_specialist):
    """Tests that the specialist raises an error if the LLM response is not valid JSON."""
    # Arrange
    text_analysis_specialist.llm_adapter.invoke.return_value = {"json_response": None}
    initial_state = {"messages": [], "artifacts": {"text_to_process": "Some text."}}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid JSON response"):
        text_analysis_specialist._execute_logic(initial_state)