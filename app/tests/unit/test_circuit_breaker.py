import pytest
from unittest.mock import MagicMock, patch
from app.src.resilience.monitor import InvariantMonitor
from app.src.utils.errors import InvariantViolationError, CircuitBreakerTriggered
from app.src.graph.state_factory import create_test_state

def test_stabilization_action_halt():
    """
    Verifies that the monitor raises CircuitBreakerTriggered when action is HALT.
    """
    config = {
        "workflow": {
            "recursion_limit": 5,
            "stabilization_actions": {
                "max_turn_count_exceeded": "HALT"
            }
        }
    }
    monitor = InvariantMonitor(config)
    state = create_test_state(turn_count=10) # Exceeds limit

    with pytest.raises(CircuitBreakerTriggered):
        monitor.check_invariants(state)

def test_stabilization_action_default_halt():
    """
    Verifies that the monitor defaults to HALT if action is not configured.
    """
    config = {
        "workflow": {
            "recursion_limit": 5,
            # No stabilization_actions configured
        }
    }
    monitor = InvariantMonitor(config)
    state = create_test_state(turn_count=10)

    with pytest.raises(CircuitBreakerTriggered):
        monitor.check_invariants(state)

def test_violation_type_detection_structure():
    """
    Verifies that structural violations are correctly identified.
    """
    config = {"workflow": {}}
    monitor = InvariantMonitor(config)
    state = create_test_state()
    del state["messages"] # Structural violation

    with patch("app.src.resilience.monitor.logger") as mock_logger:
        with pytest.raises(CircuitBreakerTriggered):
            monitor.check_invariants(state)

        # Check logs for correct violation type detection
        # We look for the log message that contains the violation type
        found = False
        for call in mock_logger.warning.call_args_list:
            if "Violation: structural_integrity_violated" in call[0][0]:
                found = True
                break
        assert found

def test_violation_type_detection_loop():
    """
    Verifies that loop violations are correctly identified.
    """
    config = {"workflow": {"max_loop_cycles": 2}}
    monitor = InvariantMonitor(config)
    # A -> A -> A (3 times, threshold 2)
    state = create_test_state(routing_history=["A", "A", "A"])

    with patch("app.src.resilience.monitor.logger") as mock_logger:
        with pytest.raises(CircuitBreakerTriggered):
            monitor.check_invariants(state)

        found = False
        for call in mock_logger.warning.call_args_list:
            if "Violation: loop_detected" in call[0][0]:
                found = True
                break
        assert found
