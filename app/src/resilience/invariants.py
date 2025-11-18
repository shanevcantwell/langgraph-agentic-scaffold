from typing import List, Any, Dict
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

def check_loop_detection(state: GraphState, threshold: int = 3) -> None:
    """
    Detects potential infinite loops in the routing history.
    Checks for:
    1. Immediate repetition of a single specialist (A -> A -> A)
    2. Repetition of a 2-step cycle (A -> B -> A -> B)
    """
    history = state["routing_history"]
    if len(history) < threshold:
        return

    # Check for immediate repetition (A -> A -> A)
    last_specialist = history[-1]
    repetition_count = 0
    for specialist in reversed(history):
        if specialist == last_specialist:
            repetition_count += 1
        else:
            break
    
    if repetition_count > threshold:
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
