import logging
from typing import Dict, Any
from langsmith import traceable
from app.src.graph.state import GraphState
from app.src.resilience.invariants import check_state_structure, check_max_turn_count, check_loop_detection
from app.src.utils.errors import InvariantViolationError, CircuitBreakerTriggered

logger = logging.getLogger(__name__)

class InvariantMonitor:
    """
    Service responsible for monitoring system invariants during workflow execution.
    Acts as a circuit breaker, halting execution if the system enters an invalid state.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.workflow_config = config.get("workflow", {})
        self.max_turns = self.workflow_config.get("recursion_limit", 40)
        self.loop_threshold = self.workflow_config.get("max_loop_cycles", 3)

    @traceable(name="InvariantMonitor.check_invariants", run_type="tool")
    def check_invariants(self, state: GraphState, stage: str = "unknown") -> None:
        """
        Runs all configured invariant checks against the current state.
        
        Args:
            state: The current GraphState.
            stage: A label for the execution stage (e.g., "pre-execution", "post-execution").
        
        Raises:
            CircuitBreakerTriggered: If an invariant is violated and an action is triggered.
        """
        try:
            # 1. Structural Integrity
            check_state_structure(state)
            
            # 2. Execution Constraints
            check_max_turn_count(state, self.max_turns)
            check_loop_detection(state, self.loop_threshold)
            
        except InvariantViolationError as e:
            logger.error(f"Invariant violation detected at stage '{stage}': {e}")
            
            # Determine the type of violation for action mapping
            violation_type = "unknown_violation"
            error_msg = str(e)
            if "Missing required state key" in error_msg or "must be a" in error_msg:
                violation_type = "structural_integrity_violated"
            elif "Max turn count exceeded" in error_msg:
                violation_type = "max_turn_count_exceeded"
            elif "Detected" in error_msg and "loop" in error_msg:
                violation_type = "loop_detected"

            # Get configured action
            stabilization_actions = self.workflow_config.get("stabilization_actions", {})
            action = stabilization_actions.get(violation_type, "HALT") # Default to HALT

            logger.warning(f"Circuit Breaker triggered! Violation: {violation_type}, Action: {action}")

            # Raise the circuit breaker exception with the determined action
            raise CircuitBreakerTriggered(action=action, reason=str(e), violation_type=violation_type)
