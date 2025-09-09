# app/tests/unit/test_router_specialist.py
import logging
from unittest.mock import MagicMock, patch
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.router_specialist import RouterSpecialist
from app.src.enums import CoreSpecialist


def test_router_specialist_two_stage_termination_logic():
    """
    Tests the Two-Stage Termination Pattern.

    1.  A specialist signals `task_is_complete`.
    2.  Router should route to `archiver_specialist` (Stage 1).
    3.  On the next turn, with `archive_report` present, Router should route to `END` (Stage 2).
    """
    # Arrange
    specialist_name = "router_specialist"
    specialist_config = {}
    router = RouterSpecialist(specialist_name, specialist_config)

    # Mock the specialist map to include the archiver
    router.set_specialist_map(
        {
            CoreSpecialist.ARCHIVER.value: {"description": "Creates a final report."},
            "some_other_specialist": {"description": "Does something else."},
        }
    )

    # --- Stage 1: Specialist signals task_is_complete ---
    initial_state = {
        "messages": [HumanMessage(content="Do the thing.")],
        "task_is_complete": True,
        "turn_count": 2,
        "routing_history": ["some_other_specialist"],
    }

    # Act - Stage 1
    stage1_result = router._execute_logic(initial_state)

    # Assert - Stage 1
    assert stage1_result["next_specialist"] == CoreSpecialist.ARCHIVER.value
    assert stage1_result["turn_count"] == 3
    assert "task_is_complete" not in stage1_result  # Should not be passed on
    ai_message_stage1 = stage1_result["messages"][0]
    assert isinstance(ai_message_stage1, AIMessage)
    assert (
        ai_message_stage1.additional_kwargs["routing_type"] == "completion_signal"
    )
    assert (
        ai_message_stage1.additional_kwargs["routing_decision"]
        == CoreSpecialist.ARCHIVER.value
    )
    logging.info("Stage 1 Test Passed: Router correctly routed to Archiver.")

    # --- Stage 2: Archiver has run, archive_report is present ---
    # Arrange - Stage 2
    state_after_archiver = {
        "messages": [
            HumanMessage(content="Do the thing."),
            AIMessage(content="Thing done.", name="some_other_specialist"),
            ai_message_stage1,
            AIMessage(
                content="Archive report generated.", name=CoreSpecialist.ARCHIVER.value
            ),
        ],
        "archive_report": "This is the final report.",
        "turn_count": 3,  # Incremented from stage 1
        "routing_history": ["some_other_specialist", CoreSpecialist.ARCHIVER.value],
    }

    # Act - Stage 2
    stage2_result = router._execute_logic(state_after_archiver)

    # Assert - Stage 2
    assert stage2_result["next_specialist"] == END
    assert stage2_result["turn_count"] == 4
    ai_message_stage2 = stage2_result["messages"][0]
    assert isinstance(ai_message_stage2, AIMessage)
    assert (
        ai_message_stage2.additional_kwargs["routing_type"] == "final_report_signal"
    )
    assert ai_message_stage2.additional_kwargs["routing_decision"] == END
    logging.info("Stage 2 Test Passed: Router correctly routed to END.")


def setup_module(module):
    """Set up logging for the test module."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )


def teardown_module(module):
    """Teardown logging for the test module."""
    logging.shutdown()
