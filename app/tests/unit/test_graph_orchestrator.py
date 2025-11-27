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
    """Tests that the function routes to END when a repeating loop is detected."""
    # Configure the instance for the test
    orchestrator_instance.max_loop_cycles = 3
    orchestrator_instance.min_loop_len = 2

    # This history represents a loop of ['A', 'B'] repeating 3 times.
    state = {
        "routing_history": ["C", "A", "B", "A", "B", "A", "B"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == CoreSpecialist.END.value

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
    """Tests that the function routes to END if the router fails to provide a next step."""
    state = create_test_state(next_specialist=None, turn_count=1)
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == CoreSpecialist.END.value

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