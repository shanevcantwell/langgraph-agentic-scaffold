import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import HumanMessage
from app.src.specialists.prompt_triage_specialist import PromptTriageSpecialist
from app.src.specialists.schemas import TriageRecommendations
from app.src.enums import CoreSpecialist
from app.src.llm.adapter import StandardizedLLMRequest

@pytest.fixture
def prompt_triage_specialist(initialized_specialist_factory):
    """Fixture for an initialized PromptTriageSpecialist."""
    specialist = initialized_specialist_factory("PromptTriageSpecialist")
    # Set a mock specialist map for testing purposes
    specialist.set_specialist_map({
        "file_specialist": {"description": "Handles file operations"},
        "web_builder": {"description": "Builds web content"},
        CoreSpecialist.DEFAULT_RESPONDER.value: {"description": "Default conversational agent"}
    })
    return specialist

def test_prompt_triage_recommends_specialists_from_llm(prompt_triage_specialist):
    """Tests that the specialist correctly recommends specialists based on LLM tool call."""
    # Arrange
    mock_recommendations = ["file_specialist", "web_builder"]
    mock_tool_call_args = {"recommended_specialists": mock_recommendations}
    prompt_triage_specialist.llm_adapter.invoke.return_value = {
        "tool_calls": [{"args": mock_tool_call_args, "id": "call_123"}]
    }

    initial_state = {"messages": [HumanMessage(content="Please create a file and then build a website.")]}

    # Act
    result_state = prompt_triage_specialist._execute_logic(initial_state)

    # Assert
    prompt_triage_specialist.llm_adapter.invoke.assert_called_once()
    called_request = prompt_triage_specialist.llm_adapter.invoke.call_args[0][0]
    assert isinstance(called_request, StandardizedLLMRequest)
    assert TriageRecommendations in called_request.tools

    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == mock_recommendations
    assert "triage_recommendations" in result_state
    assert result_state["triage_recommendations"] == mock_recommendations
    assert "messages" not in result_state # Triage should not add conversational messages

def test_prompt_triage_falls_back_to_default_responder_on_no_tool_call(prompt_triage_specialist):
    """Tests fallback to default_responder when LLM provides no valid tool call."""
    # Arrange
    prompt_triage_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}

    initial_state = {"messages": [HumanMessage(content="Just chat with me.")]}

    # Act
    result_state = prompt_triage_specialist._execute_logic(initial_state)

    # Assert
    prompt_triage_specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["recommended_specialists"] == [CoreSpecialist.DEFAULT_RESPONDER.value]
    assert result_state["triage_recommendations"] == [CoreSpecialist.DEFAULT_RESPONDER.value]

def test_prompt_triage_filters_invalid_recommendations(prompt_triage_specialist):
    """Tests that the specialist filters out recommendations not in its map."""
    # Arrange
    mock_recommendations = ["file_specialist", "non_existent_specialist", "web_builder"]
    mock_tool_call_args = {"recommended_specialists": mock_recommendations}
    prompt_triage_specialist.llm_adapter.invoke.return_value = {
        "tool_calls": [{"args": mock_tool_call_args, "id": "call_123"}]
    }

    initial_state = {"messages": [HumanMessage(content="Do something.")]}

    # Act
    result_state = prompt_triage_specialist._execute_logic(initial_state)

    # Assert
    assert result_state["recommended_specialists"] == ["file_specialist", "web_builder"]
    assert result_state["triage_recommendations"] == ["file_specialist", "web_builder"]

def test_prompt_triage_handles_empty_recommendations_list(prompt_triage_specialist):
    """Tests fallback to default_responder when LLM returns an empty list of recommendations."""
    # Arrange
    mock_tool_call_args = {"recommended_specialists": []}
    prompt_triage_specialist.llm_adapter.invoke.return_value = {
        "tool_calls": [{"args": mock_tool_call_args, "id": "call_123"}]
    }

    initial_state = {"messages": [HumanMessage(content="Do something.")]}

    # Act
    result_state = prompt_triage_specialist._execute_logic(initial_state)

    # Assert
    assert result_state["recommended_specialists"] == [CoreSpecialist.DEFAULT_RESPONDER.value]
    assert result_state["triage_recommendations"] == [CoreSpecialist.DEFAULT_RESPONDER.value]

def test_prompt_triage_no_specialist_map_configured(initialized_specialist_factory):
    """Tests behavior when specialist_map is empty."""
    # Arrange
    specialist = initialized_specialist_factory("PromptTriageSpecialist")
    specialist.specialist_map = {} # Explicitly empty map

    initial_state = {"messages": [HumanMessage(content="Test.")]}

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called() # LLM should not be called
    assert result_state["recommended_specialists"] == []