import logging
import re
from typing import Dict, Any, Optional
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

    def _extract_forbidden_specialists_from_error(self, error_msg: str) -> list[str]:
        """
        Extracts specialist names from loop detection error messages.

        Handles four cases:
        1. Stagnation detected: "Stagnation detected: 'specialist_name' producing identical output..."
        2. Max iterations exceeded: "Max iterations exceeded: 'specialist_name' repeated N > M"
        3. Immediate repetition: "Detected immediate loop: 'specialist_name' repeated N times"
        4. 2-step cycle: "Detected 2-step cycle loop: ['specialist_a', 'specialist_b'] repeated N times"

        Returns:
            List of specialist names to forbid
        """
        # Case 1 & 2 & 3: Single specialist in quotes (stagnation, max_iterations, immediate loop)
        # More general pattern that catches all single-specialist error formats
        single_specialist_match = re.search(r"'([^']+)'", error_msg)
        if single_specialist_match and "[" not in error_msg:  # Exclude 2-step cycle pattern
            specialist_name = single_specialist_match.group(1)
            return [specialist_name]

        # Case 4: 2-step cycle - extract both specialists from pattern
        cycle_match = re.search(r"Detected 2-step cycle loop: \[([^\]]+)\]", error_msg)
        if cycle_match:
            # Parse the list content: "'specialist_a', 'specialist_b'"
            list_content = cycle_match.group(1)
            specialists = re.findall(r"'([^']+)'", list_content)
            return specialists

        # Fallback: couldn't parse, return empty list
        logger.warning(f"Could not extract specialist names from loop error: {error_msg}")
        return []

    @traceable(name="InvariantMonitor.check_invariants", run_type="tool")
    def check_invariants(self, state: GraphState, stage: str = "unknown") -> Optional[Dict[str, Any]]:
        """
        Runs all configured invariant checks against the current state.

        ADR-CORE-016: Menu Filter Pattern (Tier 1)
        - If loop detected and menu filter enabled: Returns state update to populate forbidden list
        - If loop detected and menu filter already active: Raises CircuitBreakerTriggered (Tier 3)
        - If other invariant violated: Raises CircuitBreakerTriggered immediately

        Args:
            state: The current GraphState.
            stage: A label for the execution stage (e.g., "pre-execution", "post-execution").

        Returns:
            Optional state update dict for menu filter activation, or None if no violations

        Raises:
            CircuitBreakerTriggered: If invariant violated and circuit breaker should activate
        """
        try:
            # 1. Structural Integrity
            check_state_structure(state)

            # 2. Execution Constraints
            check_max_turn_count(state, self.max_turns)
            check_loop_detection(state, self.loop_threshold, config=self.config)

            return None  # No violations

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

            # ADR-CORE-016: Menu Filter Pattern (Tier 1) - Loop Recovery
            if violation_type == "loop_detected":
                menu_filter_enabled = self.workflow_config.get("enable_menu_filter", True)

                if menu_filter_enabled:
                    # Check if menu filter already active (Tier 1 failed, escalate to Tier 3)
                    scratchpad = state.get("scratchpad", {})
                    forbidden_already_active = scratchpad.get("forbidden_specialists") is not None

                    if forbidden_already_active:
                        logger.error("TIER 3: Circuit Breaker - Menu filter already active but loop persists")
                        raise CircuitBreakerTriggered(
                            action="HALT",
                            reason=f"Loop detected after menu filter applied: {error_msg}",
                            violation_type="loop_detected_tier3"
                        )

                    # TIER 1: Activate Menu Filter - Extract specialists to forbid
                    forbidden_specialists = self._extract_forbidden_specialists_from_error(error_msg)

                    if forbidden_specialists:
                        logger.warning(f"TIER 1: Menu Filter - Forbidding {forbidden_specialists} for next routing decision")
                        return {
                            "scratchpad": {
                                "forbidden_specialists": forbidden_specialists,
                                "loop_detection_reason": error_msg
                            }
                        }
                    else:
                        logger.error("TIER 1: Menu Filter - Could not extract specialists from error, escalating to circuit breaker")
                        # Fall through to circuit breaker

            # Circuit Breaker (Tier 3 or menu filter disabled)
            stabilization_actions = self.workflow_config.get("stabilization_actions", {})
            action = stabilization_actions.get(violation_type, "HALT")

            logger.warning(f"Circuit Breaker triggered! Violation: {violation_type}, Action: {action}")
            raise CircuitBreakerTriggered(action=action, reason=str(e), violation_type=violation_type)
