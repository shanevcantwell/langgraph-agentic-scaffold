# app/tests/unit/test_text_analysis_specialist.py
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.text_analysis_specialist import TextAnalysisSpecialist

def test_text_analysis_with_text():
    """
    Tests the normal execution path where text is provided and successfully analyzed.
    """
    # Arrange
    specialist = TextAnalysisSpecialist("text_analysis_specialist")
    specialist.llm_adapter = MagicMock()
    mock_response = {"summary": "Test summary", "main_points": ["Point 1", "Point 2"]}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Analyze this.")],
        "text_to_process": "This is the text to analyze."
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_called_once()
    assert "json_artifact" in result_state
    assert result_state["json_artifact"] == mock_response
    assert result_state["text_to_process"] is None # Should be consumed
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Test summary" in result_state["messages"][0].content

def test_text_analysis_without_text_self_correction():
    """
    Tests the self-correction mechanism where no text is provided.
    """
    # Arrange
    specialist = TextAnalysisSpecialist("text_analysis_specialist")
    specialist.llm_adapter = MagicMock() # Mock the adapter

    initial_state = {"messages": [HumanMessage(content="Analyze this.")]}

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called() # LLM should not be called
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["file_specialist"]
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I cannot run because there is no text to process" in result_state["messages"][0].content