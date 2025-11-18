import pytest
from app.src.resilience.invariants import check_state_structure, check_max_turn_count, check_loop_detection
from app.src.utils.errors import InvariantViolationError
from app.src.graph.state_factory import create_test_state

def test_check_state_structure_valid():
    state = create_test_state()
    # Should not raise
    check_state_structure(state)

def test_check_state_structure_missing_key():
    state = create_test_state()
    del state["messages"]
    with pytest.raises(InvariantViolationError, match="Missing required state key: messages"):
        check_state_structure(state)

def test_check_state_structure_invalid_type():
    state = create_test_state()
    state["messages"] = "not a list"
    with pytest.raises(InvariantViolationError, match="State 'messages' must be a list"):
        check_state_structure(state)

def test_check_max_turn_count_valid():
    state = create_test_state(turn_count=5)
    check_max_turn_count(state, max_turns=10)

def test_check_max_turn_count_exceeded():
    state = create_test_state(turn_count=11)
    with pytest.raises(InvariantViolationError, match="Max turn count exceeded"):
        check_max_turn_count(state, max_turns=10)

def test_check_loop_detection_no_loop():
    state = create_test_state(routing_history=["A", "B", "C"])
    check_loop_detection(state, threshold=3)

def test_check_loop_detection_immediate_loop():
    # A -> A -> A -> A (4 times, threshold 3)
    state = create_test_state(routing_history=["A", "A", "A", "A"])
    with pytest.raises(InvariantViolationError, match="Detected immediate loop"):
        check_loop_detection(state, threshold=3)

def test_check_loop_detection_immediate_loop_below_threshold():
    # A -> A -> A (3 times, threshold 3)
    state = create_test_state(routing_history=["A", "A", "A"])
    check_loop_detection(state, threshold=3)

def test_check_loop_detection_2step_cycle():
    # A -> B -> A -> B -> A -> B -> A -> B (4 times, threshold 3)
    state = create_test_state(routing_history=["A", "B", "A", "B", "A", "B", "A", "B"])
    with pytest.raises(InvariantViolationError, match="Detected 2-step cycle loop"):
        check_loop_detection(state, threshold=3)

def test_check_loop_detection_2step_cycle_below_threshold():
    # A -> B -> A -> B -> A -> B (3 times, threshold 3)
    state = create_test_state(routing_history=["A", "B", "A", "B", "A", "B"])
    check_loop_detection(state, threshold=3)
