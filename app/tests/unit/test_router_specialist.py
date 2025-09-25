# Audited on Sept 23, 2025
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


def test_router_specialist_three_stage_termination_logic():
    """
    Tests the Three-Stage Termination Pattern.

    1.  A specialist signals `task_is_complete`. The router should not see this directly.
    2.  Router should route to `response_synthesizer_specialist` (Stage 1).
    3.  On a subsequent turn, with `archive_report.md` present, Router should route to `END` (Stage 3).
    """
    # Arrange
    specialist_name = "router_specialist"
    specialist_config = {}
    router = RouterSpecialist(specialist_name, specialist_config)
    router.llm_adapter = MagicMock() # Add mock adapter to prevent errors
    # Mock the specialist map to include the archiver
    router.set_specialist_map(
        {
            CoreSpecialist.RESPONSE_SYNTHESIZER.value: {"description": "Synthesizes a response."},
            CoreSpecialist.ARCHIVER.value: {"description": "Creates a final report."},
            "some_other_specialist": {"description": "Does something else."},
        }
    )

    # --- Stage 2: final_user_response.md is present, route to archiver ---
    initial_state = {
        "messages": [HumanMessage(content="Do the thing.")],
        "artifacts": {"final_user_response.md": "This is the final response."},
        "turn_count": 2,
        "routing_history": ["some_other_specialist"],
    }

    # Act - Stage 1
    stage1_result = router._execute_logic(initial_state)

    # Assert - Stage 1
    assert stage1_result["next_specialist"] == CoreSpecialist.ARCHIVER.value
    assert stage1_result.get("turn_count", 0) == 3
    ai_message_stage1 = stage1_result["messages"][0]
    assert isinstance(ai_message_stage1, AIMessage)
    assert (
        stage1_result["messages"][0].additional_kwargs["routing_type"] == "final_response_signal"
    )
    assert (
        stage1_result["messages"][0].additional_kwargs["routing_decision"]
        == CoreSpecialist.ARCHIVER.value
    )
    logging.info("Stage 2 Test Passed: Router correctly routed to Response Synthesizer.")

    # --- Stage 3: Archiver has run, archive_report.md is present ---
    # Arrange - Stage 3
    # This state simulates the graph *after* the archiver has run.
    state_after_archiver = {
        "messages": [
            HumanMessage(content="Do the thing."),
            AIMessage(content="Thing done.", name="some_other_specialist"),
            ai_message_stage1,
            AIMessage(
                content="Archive report generated.", name=CoreSpecialist.ARCHIVER.value
            ),
        ],
        "turn_count": 3,  # Incremented from stage 1
        "routing_history": ["some_other_specialist", CoreSpecialist.ARCHIVER.value],
        "artifacts": {"archive_report.md": "This is the final report."}
    }

    # Act - Stage 3
    stage2_result = router._execute_logic(state_after_archiver)

    # Assert - Stage 3
    assert stage2_result["next_specialist"] == END
    assert stage2_result.get("turn_count", 0) == 4
    ai_message_stage2 = stage2_result["messages"][0]
    assert isinstance(ai_message_stage2, AIMessage)
    assert (
        stage2_result["messages"][0].additional_kwargs["routing_type"] == "final_report_signal"
    )
    assert stage2_result["messages"][0].additional_kwargs["routing_decision"] == END
    logging.info("Stage 3 Test Passed: Router correctly routed to END.")

def test_router_normal_llm_routing(router_specialist):
    """
    Tests the primary path where the router uses the LLM to decide the next specialist.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": "file_specialist", "rationale": "User wants to read a file."}
    }

    initial_state = {
        "messages": [HumanMessage(content="Please read my_file.txt")],
        "turn_count": 1,
        "routing_history": [],
        "task_is_complete": False,

    }

    # Act
    result = router._execute_logic(initial_state)

    # Assert
    mock_adapter.invoke.assert_called_once()
    assert result["next_specialist"] == "file_specialist"
    assert result.get("turn_count", 0) == 2
    ai_message = result["messages"][0]
    assert isinstance(ai_message, AIMessage)
    assert ai_message.additional_kwargs["routing_type"] == "llm_choice"
    assert "User wants to read a file." in ai_message.content

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
        "json_response": {"next_specialist": "non_existent_specialist", "rationale": "Hallucinated."}
    }

    initial_state = {"messages": [HumanMessage(content="Do something weird")]}

    # Act
    result = router_specialist._execute_logic(initial_state)

    # Assert
    assert result["next_specialist"] == "router_specialist" # Should re-route to itself
    ai_message = result["messages"][0]
    assert "Self-correction" in ai_message.content
    assert "non_existent_specialist" in ai_message.content

def test_router_stage_2_routes_to_archiver(router_specialist):
    """
    Tests Stage 2 of termination: after response synthesis, route to the archiver.
    """
    # Arrange
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {"description": "Archives things"}})

    # State after ResponseSynthesizer has run, but before Archiver
    state_after_synthesis = {
        "artifacts": {"final_user_response.md": "This is the final response."},
        "messages": [HumanMessage(content="Do the thing.")],
        "routing_history": [CoreSpecialist.RESPONSE_SYNTHESIZER.value]
    }

    # Act
    result = router_specialist._execute_logic(state_after_synthesis)

    # Assert
    assert result["next_specialist"] == CoreSpecialist.ARCHIVER.value

def setup_module(module):
    """Set up logging for the test module."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )


def teardown_module(module):
    """Teardown logging for the test module."""
    logging.shutdown()
