# app/tests/unit/test_router_specialist.py
import pytest
import logging
from unittest.mock import MagicMock, patch, ANY
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.router_specialist import RouterSpecialist
from app.src.utils.errors import LLMInvocationError
from app.src.enums import CoreSpecialist

@pytest.fixture
def router_specialist(initialized_specialist_factory):
    """Fixture for an initialized RouterSpecialist."""
    return initialized_specialist_factory("RouterSpecialist")

# --- Fine-Grained Unit Tests for Helper Methods ---

def test_get_available_specialists_no_recommendations(router_specialist):
    """Tests that all specialists are returned when no recommendations are present."""
    # Arrange
    router_specialist.set_specialist_map({
        "spec1": {"desc": "d1"},
        "spec2": {"desc": "d2"}
    })
    state = {"messages": []} # No recommended_specialists
    # Act
    available = router_specialist._get_available_specialists(state)
    # Assert
    assert "spec1" in available
    assert "spec2" in available
    assert len(available) == 2

def test_get_available_specialists_with_recommendations(router_specialist):
    """Tests that the specialist list is filtered by recommendations."""
    # Arrange
    router_specialist.set_specialist_map({
        "spec1": {"desc": "d1"},
        "spec2": {"desc": "d2"},
        "spec3": {"desc": "d3"}
    })
    state = {"recommended_specialists": ["spec1", "spec3"]}
    # Act
    available = router_specialist._get_available_specialists(state)
    # Assert
    assert "spec1" in available
    assert "spec3" in available
    assert "spec2" not in available
    assert len(available) == 2

def test_handle_llm_failure_fallback_priority(router_specialist):
    """Tests the fallback logic when the LLM fails to make a decision."""
    # Case 1: Default Responder is available
    router_specialist.set_specialist_map({CoreSpecialist.DEFAULT_RESPONDER.value: {}, CoreSpecialist.ARCHIVER.value: {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == CoreSpecialist.DEFAULT_RESPONDER.value

    # Case 2: No Default Responder, Archiver is available
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == CoreSpecialist.ARCHIVER.value

    # Case 3: No fallbacks available
    router_specialist.set_specialist_map({"some_other_specialist": {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == END

def test_validate_llm_choice(router_specialist):
    """Tests the validation of the LLM's routing choice."""
    valid_options = ["spec1", "spec2"]

    # Case 1: Valid choice
    choice = router_specialist._validate_llm_choice("spec1", valid_options)
    assert choice == "spec1"

    # Case 2: Invalid choice
    choice = router_specialist._validate_llm_choice("invalid_spec", valid_options)
    assert choice == CoreSpecialist.DEFAULT_RESPONDER.value


# --- Integration-Style Tests for _execute_logic ---

def test_router_stage_3_termination_logic(router_specialist):
    """
    Tests Stage 3 of termination: when an archive report is present, the router
    should route to the special END node to terminate the graph.
    """
    # Arrange
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {"description": "Archives things"}})
    state_after_archiver = {
        "messages": [
            HumanMessage(content="Do the thing."),
            AIMessage(
                content="Archive report generated.", name=CoreSpecialist.ARCHIVER.value
            ),
        ],
        "turn_count": 3,
        "routing_history": ["some_other_specialist", CoreSpecialist.ARCHIVER.value],
        "artifacts": {"archive_report.md": "This is the final report."}
    }

    # Act - Stage 3
    result = router_specialist._execute_logic(state_after_archiver)

    # Assert - Stage 3
    # The router should recognize the presence of the archive report and route to END.
    assert result["next_specialist"] == END


def test_router_normal_llm_routing(router_specialist):
    """
    Tests the primary path where the router uses the LLM to decide the next specialist.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.return_value = {
        "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_123"}]
    }

    initial_state = {
        "messages": [HumanMessage(content="Please read my_file.txt")],
        "turn_count": 1,
        "routing_history": [],
        "task_is_complete": False,

    }

    # Act
    result = router_specialist._execute_logic(initial_state)

    # Assert
    mock_adapter.invoke.assert_called_once()
    assert result["next_specialist"] == "file_specialist"
    assert result.get("turn_count", 0) == 2
    ai_message = result["messages"][0]
    assert isinstance(ai_message, AIMessage)
    assert ai_message.additional_kwargs["routing_type"] == "llm_decision"
    assert "Routing to specialist: file_specialist" in ai_message.content

def test_router_handles_llm_invocation_error(router_specialist):
    """
    Tests that the router propagates an LLMInvocationError if the adapter fails.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.side_effect = LLMInvocationError("API is down")

    initial_state = {"messages": [HumanMessage(content="Read a file")]}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        router_specialist._execute_logic(initial_state)

def test_router_handles_invalid_llm_response(router_specialist):
    """
    Tests that the router self-corrects if the LLM returns an invalid specialist name.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.return_value = {
        "tool_calls": [{"args": {"next_specialist": "non_existent_specialist"}, "id": "call_123"}]
    }

    initial_state = {"messages": [HumanMessage(content="Do something weird")]}

    # Act
    result = router_specialist._execute_logic(initial_state)

    # Assert
    assert result["next_specialist"] == CoreSpecialist.DEFAULT_RESPONDER.value
    # The router now logs the self-correction but the AI message is a standard routing message
    ai_message = result["messages"][0]
    assert "Routing to specialist: default_responder_specialist" in ai_message.content
    assert ai_message.additional_kwargs["routing_type"] == "llm_decision" # It's still an LLM decision, just a corrected one.

def test_router_stage_2_routes_to_archiver(router_specialist):
    """
    Tests Stage 2 of termination: after response synthesis, route to the archiver.
    """
    # Arrange
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {"description": "Archives things"}, CoreSpecialist.RESPONSE_SYNTHESIZER.value: {"description": "Synthesizes"}})

    # State after ResponseSynthesizer has run, but before Archiver
    state_after_synthesis = {
        "artifacts": {"final_user_response.md": "This is the final response."},
        "messages": [HumanMessage(content="Do the thing.")],
        "routing_history": ["some_other_specialist", CoreSpecialist.RESPONSE_SYNTHESIZER.value]
    }

    # Act
    result = router_specialist._execute_logic(state_after_synthesis)

    # Assert
    # This test is currently failing because the router logic doesn't yet
    # have the pre-LLM check for this termination condition.
    # The router should see the final response and route to the archiver.
    assert result["next_specialist"] == CoreSpecialist.ARCHIVER.value

def setup_module(module):
    """Set up logging for the test module."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )


def teardown_module(module):
    """Teardown logging for the test module."""
    logging.shutdown()
