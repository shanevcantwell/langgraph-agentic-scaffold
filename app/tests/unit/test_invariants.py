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


# ========================================
# Progressive Loop Detection Tests
# (Three-Check Logic: Identity → Config → Stagnation)
# ========================================

def test_progressive_loop_detection_productive_iteration_allowed():
    """
    PRODUCTIVE ITERATION: Specialist repeats but produces different outputs (making progress).
    Expected: NO ERROR (iteration allowed, outputs differ, within max_iterations).
    """
    # researcher repeated 5 times with DIFFERENT output hashes
    routing_history = ["researcher_specialist"] * 5
    output_hashes = {
        "researcher_specialist": ["hash1", "hash2", "hash3"]  # Last 3 hashes, all different
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "researcher_specialist": {
                "allows_iteration": True,
                "max_iterations": 10,
                "detect_stagnation": True
            }
        }
    }

    # Should NOT raise (productive iteration in progress)
    check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_stagnation_detected_kills_fast():
    """
    STAGNATION: Specialist repeats with SAME output (stuck loop).
    Expected: InvariantViolationError with 'Stagnation detected' after 4 repetitions (threshold+1).
    """
    # researcher repeated 4 times with SAME output hash
    routing_history = ["researcher_specialist"] * 4
    output_hashes = {
        "researcher_specialist": ["hash1", "hash1", "hash1"]  # Last 3 hashes, all IDENTICAL
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "researcher_specialist": {
                "allows_iteration": True,
                "max_iterations": 20,  # High limit, but stagnation kills faster
                "detect_stagnation": True
            }
        }
    }

    # Should raise stagnation error (same output = no progress)
    with pytest.raises(InvariantViolationError, match="Stagnation detected.*producing identical output"):
        check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_max_iterations_exceeded():
    """
    MAX ITERATIONS: Specialist exceeds max_iterations cap despite making progress.
    Expected: InvariantViolationError with 'Max iterations exceeded'.
    """
    # researcher repeated 21 times with different outputs
    routing_history = ["researcher_specialist"] * 21
    output_hashes = {
        "researcher_specialist": ["hash19", "hash20", "hash21"]  # Different hashes (progress)
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "researcher_specialist": {
                "allows_iteration": True,
                "max_iterations": 20,
                "detect_stagnation": True
            }
        }
    }

    # Should raise max iterations error
    with pytest.raises(InvariantViolationError, match="Max iterations exceeded.*repeated 21 > 20"):
        check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_stagnation_check_disabled():
    """
    STAGNATION CHECK DISABLED: Specialist repeats with same output but detect_stagnation=False.
    Expected: NO ERROR (stagnation check disabled, only max_iterations enforced).
    """
    # researcher repeated 5 times with SAME output
    routing_history = ["researcher_specialist"] * 5
    output_hashes = {
        "researcher_specialist": ["hash1", "hash1", "hash1"]  # Identical hashes
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "researcher_specialist": {
                "allows_iteration": True,
                "max_iterations": 10,
                "detect_stagnation": False  # Disabled
            }
        }
    }

    # Should NOT raise (stagnation detection disabled)
    check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_non_iterative_specialist_standard_check():
    """
    NON-ITERATIVE SPECIALIST: No iteration config, standard loop detection applies.
    Expected: InvariantViolationError with 'Detected immediate loop'.
    """
    # chat_specialist repeated 4 times (no iteration allowance)
    routing_history = ["chat_specialist"] * 4
    state = create_test_state(routing_history=routing_history)

    config = {
        "specialists": {
            "chat_specialist": {
                "allows_iteration": False  # Default behavior
            }
        }
    }

    # Should raise standard loop detection error
    with pytest.raises(InvariantViolationError, match="Detected immediate loop.*'chat_specialist'"):
        check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_insufficient_hash_history():
    """
    INSUFFICIENT HISTORY: Not enough hashes for stagnation comparison (< 2 hashes).
    Expected: NO ERROR (stagnation check requires 2+ hashes in history).
    """
    # researcher repeated 4 times, but only 1 hash in history
    routing_history = ["researcher_specialist"] * 4
    output_hashes = {
        "researcher_specialist": ["hash1"]  # Only 1 hash (insufficient for comparison)
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "researcher_specialist": {
                "allows_iteration": True,
                "max_iterations": 10,
                "detect_stagnation": True
            }
        }
    }

    # Should NOT raise (not enough hash history for stagnation check)
    check_loop_detection(state, threshold=3, config=config)


def test_progressive_loop_detection_no_config_fallback_to_standard():
    """
    NO CONFIG PROVIDED: Falls back to standard loop detection.
    Expected: InvariantViolationError with 'Detected immediate loop'.
    """
    # specialist_x repeated 4 times, no config provided
    routing_history = ["specialist_x"] * 4
    state = create_test_state(routing_history=routing_history)

    # No config parameter passed
    with pytest.raises(InvariantViolationError, match="Detected immediate loop"):
        check_loop_detection(state, threshold=3, config=None)


def test_progressive_loop_detection_mixed_specialists_with_iteration():
    """
    MIXED ROUTING: Non-iterative specialist A interspersed with iterative specialist B.
    Expected: NO ERROR (B is making progress, A doesn't repeat consecutively).
    """
    # Pattern: A -> B -> B -> B -> B -> A
    routing_history = ["A", "B", "B", "B", "B", "A"]
    output_hashes = {
        "B": ["hash1", "hash2", "hash3"]  # B making progress
    }
    state = create_test_state(
        routing_history=routing_history,
        scratchpad={"output_hashes": output_hashes}
    )

    config = {
        "specialists": {
            "B": {
                "allows_iteration": True,
                "max_iterations": 10,
                "detect_stagnation": True
            }
        }
    }

    # Should NOT raise (B is making progress, A doesn't loop)
    check_loop_detection(state, threshold=3, config=config)
