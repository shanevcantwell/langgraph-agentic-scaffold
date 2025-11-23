import hashlib
from typing import List, Any, Dict, Optional
from app.src.graph.state import GraphState
from app.src.utils.errors import InvariantViolationError

def check_state_structure(state: GraphState) -> None:
    """
    Verifies the structural integrity of the GraphState.
    Ensures all required keys exist and are of the correct type.
    """
    required_keys = ["messages", "routing_history", "turn_count", "task_is_complete", "artifacts", "scratchpad"]
    for key in required_keys:
        if key not in state:
            raise InvariantViolationError(f"Missing required state key: {key}")
    
    if not isinstance(state["messages"], list):
        raise InvariantViolationError("State 'messages' must be a list.")
    
    if not isinstance(state["routing_history"], list):
        raise InvariantViolationError("State 'routing_history' must be a list.")
        
    if not isinstance(state["artifacts"], dict):
        raise InvariantViolationError("State 'artifacts' must be a dictionary.")
        
    if not isinstance(state["scratchpad"], dict):
        raise InvariantViolationError("State 'scratchpad' must be a dictionary.")

def check_max_turn_count(state: GraphState, max_turns: int) -> None:
    """
    Verifies that the turn count has not exceeded the maximum limit.
    """
    if state["turn_count"] > max_turns:
        raise InvariantViolationError(f"Max turn count exceeded: {state['turn_count']} > {max_turns}")

def _compute_output_hash(state: GraphState) -> str:
    """
    Compute hash of specialist's last output for stagnation detection.
    Hashes the content of the last AIMessage to detect identical outputs.

    Returns:
        MD5 hash of last message content, or empty string if no messages
    """
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "content"):
            content = last_message.content
            # Normalize: strip whitespace for consistent hashing
            normalized = content.strip()
            return hashlib.md5(normalized.encode()).hexdigest()
    return ""


def _is_stagnant(state: GraphState, specialist_name: str) -> bool:
    """
    Check if specialist's last output matches previous output (stagnation).

    Args:
        state: Current GraphState
        specialist_name: Name of specialist to check

    Returns:
        True if last 2 outputs are identical (stagnation detected)
        False if outputs differ or not enough history
    """
    output_hashes = state.get("scratchpad", {}).get("output_hashes", {})
    history = output_hashes.get(specialist_name, [])

    if len(history) < 2:
        return False  # Not enough history to detect stagnation

    # Compare last 2 hashes
    return history[-1] == history[-2]


def _get_specialist_config(config: Optional[Dict], specialist_name: str) -> Dict:
    """
    Extract specialist configuration from config dict.

    Args:
        config: Full configuration dict (from InvariantMonitor)
        specialist_name: Name of specialist to lookup

    Returns:
        Specialist config dict, or empty dict if not found
    """
    if not config:
        return {}

    specialists_config = config.get("specialists", {})
    return specialists_config.get(specialist_name, {})


def check_loop_detection(state: GraphState, threshold: int = 3, config: Optional[Dict] = None) -> None:
    """
    Detects potential infinite loops in the routing history.

    Three-Check Logic (Progressive Loop Detection):
    1. Identity Check: Is specialist repeated > threshold?
    2. Config Check: Does specialist allow iteration?
    3. Stagnation Check: Is output identical to last execution?

    Checks for:
    - Immediate repetition of a single specialist (A -> A -> A)
    - Repetition of a 2-step cycle (A -> B -> A -> B)

    With progressive detection, allows productive iteration (different outputs)
    while killing stuck loops (same output) fast.

    Args:
        state: Current GraphState
        threshold: Number of repetitions before triggering check (default: 3)
        config: Optional full config dict for specialist iteration settings
    """
    history = state["routing_history"]
    if len(history) < threshold:
        return

    # Check 1: IDENTITY - Immediate repetition (A -> A -> A)
    last_specialist = history[-1]
    repetition_count = 0
    for specialist in reversed(history):
        if specialist == last_specialist:
            repetition_count += 1
        else:
            break

    if repetition_count > threshold:
        # Check 2: CONFIG - Does specialist allow iteration?
        specialist_config = _get_specialist_config(config, last_specialist)
        allows_iteration = specialist_config.get("allows_iteration", False)

        if allows_iteration:
            # Check 3: STAGNATION - Is output identical?
            detect_stagnation = specialist_config.get("detect_stagnation", True)

            if detect_stagnation:
                if _is_stagnant(state, last_specialist):
                    # STAGNATION: Same output, no progress
                    raise InvariantViolationError(
                        f"Stagnation detected: '{last_specialist}' producing identical output "
                        f"despite {repetition_count} executions (allows_iteration=True but no progress)"
                    )
                else:
                    # PROGRESS: Different output, check max_iterations cap
                    max_iters = specialist_config.get("max_iterations", 10)
                    if repetition_count > max_iters:
                        raise InvariantViolationError(
                            f"Max iterations exceeded: '{last_specialist}' repeated {repetition_count} > {max_iters}"
                        )
                    # else: within iteration limit, making progress, allow
                    return
            else:
                # No stagnation check, just enforce max_iterations
                max_iters = specialist_config.get("max_iterations", 10)
                if repetition_count > max_iters:
                    raise InvariantViolationError(
                        f"Max iterations exceeded: '{last_specialist}' repeated {repetition_count} > {max_iters}"
                    )
                return

        # Standard loop detection for non-iterative specialists
        raise InvariantViolationError(f"Detected immediate loop: '{last_specialist}' repeated {repetition_count} times.")

    # Check for 2-step cycle (A -> B -> A -> B -> A -> B)
    # We need at least 2 * (threshold + 1) items to detect > threshold cycles
    if len(history) >= 2 * (threshold + 1):
        # Get the last 2 items
        pattern = history[-2:]
        # Ensure pattern isn't just [A, A] (which is covered by immediate repetition)
        if pattern[0] == pattern[1]:
            return 

        cycle_detected = True
        # Check for threshold + 1 repetitions
        for i in range(threshold + 1):
            # Check the slice corresponding to the i-th repetition from the end
            # history[-2:] is the last one (i=0)
            start = -2 * (i + 1)
            end = -2 * i if i > 0 else None
            
            segment = history[start:end]
            if segment != pattern:
                cycle_detected = False
                break
        
        if cycle_detected:
             raise InvariantViolationError(f"Detected 2-step cycle loop: {pattern} repeated {threshold + 1} times.")
