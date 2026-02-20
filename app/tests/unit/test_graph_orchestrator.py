# app/tests/unit/test_graph_orchestrator.py

from unittest.mock import MagicMock
import pytest

from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import SpecialistError, WorkflowError
from app.src.enums import CoreSpecialist
from app.src.graph.state_factory import create_test_state

@pytest.fixture
def orchestrator_instance():
    """Provides a GraphOrchestrator instance for testing."""
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {}
    orchestrator = GraphOrchestrator(config, specialists)
    return orchestrator

@pytest.fixture
def orchestrator_with_allowed_destinations():
    """Provides a GraphOrchestrator instance with route validation enabled."""
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {
        "file_specialist": MagicMock(),
        "chat_specialist": MagicMock(),
        "default_responder": MagicMock(),
        "progenitor_alpha_specialist": MagicMock(),
        "progenitor_bravo_specialist": MagicMock(),
        "tiered_synthesizer_specialist": MagicMock()
    }
    # Router is excluded from allowed destinations
    allowed_destinations = {"file_specialist", "chat_specialist", "default_responder",
                           "progenitor_alpha_specialist", "progenitor_bravo_specialist",
                           "tiered_synthesizer_specialist"}
    orchestrator = GraphOrchestrator(config, specialists, allowed_destinations)
    return orchestrator

def test_route_to_next_specialist_normal_route(orchestrator_instance):
    """Tests that the function returns the correct specialist name from the state."""
    state = create_test_state(next_specialist="file_specialist", turn_count=1)
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "file_specialist"

def test_route_to_next_specialist_detects_loop(orchestrator_instance):
    """Tests that the function routes to exit_interview when a repeating loop is detected.

    ADR-ROADMAP-001 Phase 1: Loop detection now routes through exit_interview
    for completion validation before terminating.
    """
    # Configure the instance for the test
    orchestrator_instance.max_loop_cycles = 3
    orchestrator_instance.min_loop_len = 2

    # This history represents a loop of ['A', 'B'] repeating 3 times.
    state = {
        "routing_history": ["C", "A", "B", "A", "B", "A", "B"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    # ADR-ROADMAP-001: Routes to exit_interview for completion check before END
    assert result == CoreSpecialist.EXIT_INTERVIEW.value

def test_route_to_next_specialist_loop_not_long_enough(orchestrator_instance):
    """Tests that a repeating pattern shorter than min_loop_len is not flagged as a loop."""
    orchestrator_instance.max_loop_cycles = 2
    orchestrator_instance.min_loop_len = 2 # A loop must be at least 2 specialists long

    # This history has a repeating 'A', but the loop length is only 1.
    state = {
        "routing_history": ["B", "A", "A", "A"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "some_specialist"

def test_route_to_next_specialist_allows_non_loop(orchestrator_instance):
    """Tests that the function does not halt for a non-looping history."""
    orchestrator_instance.max_loop_cycles = 2
    orchestrator_instance.min_loop_len = 2

    state = {
        "routing_history": ["A", "B", "C", "D"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "some_specialist"

def test_route_to_next_specialist_handles_no_route(orchestrator_instance):
    """Tests that the function routes to exit_interview if the router fails to provide a next step.

    ADR-ROADMAP-001 Phase 1: No-route cases now route through exit_interview
    for completion validation before terminating.
    """
    state = create_test_state(next_specialist=None, turn_count=1)
    result = orchestrator_instance.route_to_next_specialist(state)
    # ADR-ROADMAP-001: Routes to exit_interview for completion check before END
    assert result == CoreSpecialist.EXIT_INTERVIEW.value

# --- TASK 1.2: Route Validation Tests (Fail-Fast on Invalid Routes) ---

def test_route_validation_blocks_invalid_destination(orchestrator_with_allowed_destinations):
    """
    Tests that route_to_next_specialist raises WorkflowError when router
    selects an invalid (non-existent) destination.

    This is TASK 1.2: Fail-fast on unknown graph routes.
    """
    # Arrange: Router selects a destination that doesn't exist in the graph
    state = create_test_state(
        next_specialist="nonexistent_specialist",
        turn_count=1
    )

    # Act & Assert: Should raise WorkflowError immediately
    with pytest.raises(WorkflowError) as exc_info:
        orchestrator_with_allowed_destinations.route_to_next_specialist(state)

    # Verify error message is clear about the problem
    error_msg = str(exc_info.value)
    assert "Invalid routing destination" in error_msg
    assert "nonexistent_specialist" in error_msg
    assert "Allowed destinations" in error_msg

def test_route_validation_allows_valid_destination(orchestrator_with_allowed_destinations):
    """
    Tests that route_to_next_specialist allows routing to valid destinations
    and validation doesn't interfere with normal operation.
    """
    # Arrange: Router selects a valid destination
    state = create_test_state(
        next_specialist="file_specialist",
        turn_count=1
    )

    # Act: Should complete successfully without raising
    result = orchestrator_with_allowed_destinations.route_to_next_specialist(state)

    # Assert: Returns the valid destination
    assert result == "file_specialist"

def test_route_validation_allows_chat_specialist_fanout(orchestrator_with_allowed_destinations):
    """
    Tests that route_to_next_specialist allows routing to chat_specialist
    and correctly fans out to progenitors, with validation of fanout destinations.
    """
    # Arrange: Router selects chat_specialist, which triggers fanout
    state = create_test_state(
        next_specialist="chat_specialist",
        turn_count=1
    )

    # Act: Should fan out to progenitors
    result = orchestrator_with_allowed_destinations.route_to_next_specialist(state)

    # Assert: Returns list of progenitor specialists (fanout)
    assert isinstance(result, list)
    assert result == ["progenitor_alpha_specialist", "progenitor_bravo_specialist"]

def test_route_validation_blocks_invalid_fanout_destination(orchestrator_with_allowed_destinations):
    """
    Tests that fanout validation catches when hardcoded fanout destinations
    are not valid graph nodes (edge case: misconfigured fanout).
    """
    # Arrange: Modify allowed_destinations to exclude one progenitor
    # This simulates a misconfiguration where fanout targets aren't loaded
    orchestrator_with_allowed_destinations.allowed_destinations.remove("progenitor_bravo_specialist")

    state = create_test_state(
        next_specialist="chat_specialist",
        turn_count=1
    )

    # Act & Assert: Should raise WorkflowError for invalid fanout
    with pytest.raises(WorkflowError) as exc_info:
        orchestrator_with_allowed_destinations.route_to_next_specialist(state)

    # Verify error message identifies the fanout problem
    error_msg = str(exc_info.value)
    assert "Invalid fanout routing" in error_msg
    assert "progenitor_bravo_specialist" in error_msg

def test_route_validation_disabled_when_no_allowed_destinations():
    """
    Tests that route validation is gracefully disabled when allowed_destinations
    is not provided (backward compatibility).
    """
    # Arrange: Create orchestrator without allowed_destinations
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {}
    orchestrator = GraphOrchestrator(config, specialists, allowed_destinations=None)

    state = create_test_state(
        next_specialist="any_specialist",  # Could be invalid, but no validation
        turn_count=1
    )

    # Act: Should not raise, validation is disabled
    result = orchestrator.route_to_next_specialist(state)

    # Assert: Returns whatever was in state (no validation)
    assert result == "any_specialist"


# =============================================================================
# Issue #111: Deferred termination_reason (Loop Detector Refactor)
# =============================================================================

class TestDeferredTerminationReason:
    """
    Issue #111: Loop detector should defer termination_reason until after
    Exit Interview validation.

    The principle: termination_reason should be a true "abort with message"
    signal, not a "suspicion pending validation" signal.

    Flow:
    1. Loop detector sets loop_detected: True (informational)
    2. Routes to Exit Interview for validation
    3. Exit Interview decides:
       - COMPLETE → task is done, no abort needed (despite loop pattern)
       - INCOMPLETE → task truly stuck, NOW set termination_reason and abort
    """

    def test_loop_detector_sets_loop_detected_not_termination_reason(self, orchestrator_instance):
        """
        Loop detector should set loop_detected (informational) instead of
        termination_reason (abort signal).
        """
        orchestrator_instance.max_loop_cycles = 3
        orchestrator_instance.min_loop_len = 2

        state = {
            "routing_history": ["C", "A", "B", "A", "B", "A", "B"],
            "next_specialist": "some_specialist",
            "scratchpad": {}
        }

        result = orchestrator_instance.route_to_next_specialist(state)

        # Should route to Exit Interview for validation
        assert result == CoreSpecialist.EXIT_INTERVIEW.value

        # Should set loop_detected (informational)
        assert "loop_detected" in state["scratchpad"]
        loop_info = state["scratchpad"]["loop_detected"]
        assert loop_info["detected"] is True
        assert loop_info["sequence"] == ["A", "B"]
        assert loop_info["cycles"] == 3

        # Should NOT set termination_reason yet
        assert "termination_reason" not in state["scratchpad"]

    def test_after_exit_interview_complete_clears_loop_detected(self, orchestrator_instance):
        """
        When Exit Interview says COMPLETE despite loop pattern, we should
        clear loop_detected and NOT set termination_reason.
        """
        state = {
            "task_is_complete": True,
            "scratchpad": {
                "loop_detected": {
                    "detected": True,
                    "sequence": ["A", "B"],
                    "cycles": 3
                }
            }
        }

        result = orchestrator_instance.after_exit_interview(state)

        # Should route to END (task is done)
        assert result == CoreSpecialist.END.value

        # loop_detected should be cleared (consumed, not acted on)
        assert "loop_detected" not in state["scratchpad"]

        # termination_reason should NOT be set (task succeeded)
        assert "termination_reason" not in state["scratchpad"]

    def test_after_exit_interview_incomplete_with_loop_sets_termination_reason(self, orchestrator_instance):
        """
        When Exit Interview says INCOMPLETE after loop detection, NOW we
        should set termination_reason and abort.
        """
        state = {
            "task_is_complete": False,
            "scratchpad": {
                "loop_detected": {
                    "detected": True,
                    "sequence": ["A", "B"],
                    "cycles": 3
                }
            }
        }

        result = orchestrator_instance.after_exit_interview(state)

        # Should route to END (abort)
        assert result == CoreSpecialist.END.value

        # termination_reason should NOW be set
        assert "termination_reason" in state["scratchpad"]
        reason = state["scratchpad"]["termination_reason"]
        assert "stuck in an unproductive loop" in reason
        assert "['A', 'B']" in reason
        assert "Exit Interview confirmed" in reason

        # loop_detected should be cleared (consumed)
        assert "loop_detected" not in state["scratchpad"]

    def test_after_exit_interview_incomplete_without_loop_routes_to_facilitator(self, orchestrator_instance):
        """
        Normal INCOMPLETE (no loop) should route to Facilitator for retry,
        not set termination_reason.
        """
        # Add facilitator to specialists so it's available
        orchestrator_instance.specialists = {"facilitator_specialist": MagicMock()}

        state = {
            "task_is_complete": False,
            "scratchpad": {}  # No loop_detected
        }

        result = orchestrator_instance.after_exit_interview(state)

        # Should route to Facilitator for retry
        assert result == "facilitator_specialist"

        # termination_reason should NOT be set
        assert "termination_reason" not in state["scratchpad"]

    def test_after_exit_interview_complete_without_loop_normal_end(self, orchestrator_instance):
        """
        Normal COMPLETE (no loop) should route to END without any special handling.
        """
        state = {
            "task_is_complete": True,
            "scratchpad": {}  # No loop_detected
        }

        result = orchestrator_instance.after_exit_interview(state)

        # Should route to END
        assert result == CoreSpecialist.END.value

        # Scratchpad should remain clean
        assert "termination_reason" not in state["scratchpad"]
        assert "loop_detected" not in state["scratchpad"]


# =============================================================================
# #179: Reject-with-cause for underspecified prompts
# =============================================================================

class TestCheckTriageOutcome:
    """
    #179: When Triage produces a plan with ONLY ask_user actions (no context-
    gathering), the prompt is underspecified. Route to EndSpecialist which
    formats the ask_user questions as a rejection message in final_user_response.
    """

    def test_ask_user_only_plan_routes_to_end(self, orchestrator_instance):
        """Ask-user-only plan = reject with cause via EndSpecialist."""
        state = {
            "scratchpad": {
                "triage_actions": [
                    {"type": "ask_user", "target": "What kind of website?",
                     "description": "Clarify website type"}
                ],
                "triage_reasoning": "Need clarification",
            }
        }

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == CoreSpecialist.END.value

    def test_multiple_ask_user_actions_route_to_end(self, orchestrator_instance):
        """Multiple ask_user questions still reject."""
        state = {
            "scratchpad": {
                "triage_actions": [
                    {"type": "ask_user", "target": "What kind of website?",
                     "description": "Clarify type"},
                    {"type": "ask_user", "target": "What content should it include?",
                     "description": "Clarify content"},
                ],
                "triage_reasoning": "Multiple clarifications needed",
            }
        }

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == CoreSpecialist.END.value

    def test_mixed_plan_routes_to_sa(self, orchestrator_instance):
        """Plan with context-gathering + ask_user routes to SA for planning (not END)."""
        state = {
            "scratchpad": {
                "triage_actions": [
                    {"type": "list_directory", "target": "/workspace",
                     "description": "Check workspace"},
                    {"type": "ask_user", "target": "What style?",
                     "description": "Clarify style"},
                ],
                "triage_reasoning": "Gather context and clarify",
            }
        }

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == "systems_architect"

    def test_context_only_plan_routes_to_sa(self, orchestrator_instance):
        """Normal context-gathering plan routes to SA for planning."""
        state = {
            "scratchpad": {
                "triage_actions": [
                    {"type": "list_directory", "target": "/workspace",
                     "description": "Check workspace"},
                ],
                "triage_reasoning": "Gather filesystem context",
            }
        }

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == "systems_architect"

    def test_empty_plan_routes_to_sa(self, orchestrator_instance):
        """Empty triage_actions routes to SA for planning."""
        state = {
            "scratchpad": {
                "triage_actions": [],
                "triage_reasoning": "Simple query, no context needed",
            }
        }

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == "systems_architect"

    def test_no_triage_actions_routes_to_sa(self, orchestrator_instance):
        """Missing triage_actions in scratchpad routes to SA for planning."""
        state = {"scratchpad": {}}

        result = orchestrator_instance.check_triage_outcome(state)
        assert result == "systems_architect"


# =============================================================================
# ADR-CORE-045: Subagent mode bypasses EI
# =============================================================================

class TestSubagentEIBypass:
    """
    ADR-CORE-045: Subagent invocations run full LAS pipeline including EI.
    "LAS as a call has to be all of LAS." Only Archiver disk write is
    suppressed via the subagent flag — EI still validates completion.
    """

    def test_subagent_routes_to_ei_on_task_complete(self, orchestrator_instance):
        """When subagent=True and task_is_complete, route to EI (same as non-subagent)."""
        state = create_test_state(
            task_is_complete=True,
            scratchpad={"subagent": True},
            routing_history=["project_director"],
        )

        result = orchestrator_instance.check_task_completion(state)
        assert result == CoreSpecialist.EXIT_INTERVIEW.value

    def test_non_subagent_routes_to_ei_on_task_complete(self, orchestrator_instance):
        """Normal (non-subagent) task_is_complete routes to EI for validation."""
        state = create_test_state(
            task_is_complete=True,
            scratchpad={},
            routing_history=["project_director"],
        )

        result = orchestrator_instance.check_task_completion(state)
        assert result == CoreSpecialist.EXIT_INTERVIEW.value

    def test_subagent_without_task_complete_does_not_bypass(self, orchestrator_instance):
        """Subagent mode only bypasses when task_is_complete is True."""
        state = create_test_state(
            task_is_complete=False,
            scratchpad={"subagent": True},
            routing_history=["project_director"],
            next_specialist="project_director",
        )

        result = orchestrator_instance.check_task_completion(state)
        # task_is_complete is False, so check_task_completion returns next specialist
        assert result != CoreSpecialist.END.value