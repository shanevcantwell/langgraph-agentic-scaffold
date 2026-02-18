"""
SignalProcessorSpecialist — Procedural interrupt classification and routing.

ADR-077: Replaces the bare classify_interrupt() function on GraphOrchestrator.
Sits between every non-terminal specialist and the routing decision layer.

This is a PROCEDURAL specialist — no LLM call. It reads routing signals from
the `signals` field (specialist-produced) and `scratchpad` (externally set),
then produces a routing decision as a clean signals snapshot.

Signal output schema:
    routing_target:  str       — destination node name (consumed by route_from_signal)
    routing_context: str|None  — why we're routing there (consumed by Facilitator for BENIGN branching)
    diagnostic:      dict|None — rich detail for archiver, EI, debugging
"""
import logging
from typing import Dict, Any

from .base import BaseSpecialist
from ..enums import CoreSpecialist

logger = logging.getLogger(__name__)


class SignalProcessorSpecialist(BaseSpecialist):
    """
    Procedural specialist that classifies routing signals and determines
    the next graph destination.

    Positioned between the Invariant Monitor and the Router — it is infrastructure,
    not a spoke specialist. SafeExecutor wrapping gives routing_history tracking,
    state_timeline entries, and error handling for free.

    Overrides set_specialist_map() to receive available specialist names,
    needed for _route_pathological fallback chain (IE → EI → Router).
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self._specialist_names: set = set()

    def set_specialist_map(self, specialist_map: Dict[str, Any]):
        """Receives available specialists for fallback routing decisions."""
        self._specialist_names = set(specialist_map.keys())
        logger.info(f"SignalProcessor: Aware of {len(self._specialist_names)} specialists")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Classify signals and produce routing decision.

        Priority chain (preserves existing classify_interrupt semantics):
        1. stabilization_action in signals  (circuit breaker)  → EI/END
        2. user_abort in scratchpad         (externally set)   → END
        3. max_iterations_exceeded in signals (PD)             → EI  (BENIGN)
        4. stagnation_detected in signals   (PD)               → IE/EI/Router (PATHOLOGICAL)
        5. artifacts present                                   → EI  (NORMAL)
        6. No artifacts, no signals                            → Router (NORMAL)
        """
        signals = state.get("signals", {})
        scratchpad = state.get("scratchpad", {})
        artifacts = state.get("artifacts", {})

        # === Priority 1: Circuit breaker stabilization ===
        if signals.get("stabilization_action") == "ROUTE_TO_ERROR_HANDLER":
            target = self._resolve_stabilization_target()
            return self._build_result(target, "circuit_breaker",
                                      f"stabilization_action: {signals.get('stabilization_action')}")

        # === Priority 2: User abort (externally set, stays in scratchpad) ===
        if scratchpad.get("user_abort"):
            return self._build_result(CoreSpecialist.END.value, "user_abort",
                                      "TERMINAL: user_abort")

        # === Priority 3: BENIGN — max iterations exceeded ===
        if signals.get("max_iterations_exceeded"):
            return self._build_result(CoreSpecialist.EXIT_INTERVIEW.value, "benign_continuation",
                                      "max_iterations_exceeded — routing through EI for feedback")

        # === Priority 4: PATHOLOGICAL — stagnation detected ===
        if signals.get("stagnation_detected"):
            target = self._route_pathological()
            return self._build_result(target, "stagnation",
                                      "stagnation_detected",
                                      diagnostic={
                                          "stagnation_tool": signals.get("stagnation_tool"),
                                          "stagnation_args": signals.get("stagnation_args"),
                                      })

        # === Priority 5: Normal flow with artifacts → EI for completion check ===
        if artifacts:
            return self._build_result(CoreSpecialist.EXIT_INTERVIEW.value, None,
                                      "artifacts present, semantic completion check")

        # === Priority 6: No artifacts, no signals → Router ===
        return self._build_result(CoreSpecialist.ROUTER.value, None,
                                  "no artifacts, no interrupt — continue workflow")

    def _resolve_stabilization_target(self) -> str:
        """Resolve circuit breaker target with fallback."""
        if CoreSpecialist.EXIT_INTERVIEW.value in self._specialist_names:
            return CoreSpecialist.EXIT_INTERVIEW.value
        return CoreSpecialist.END.value

    def _route_pathological(self) -> str:
        """
        Fallback chain for pathological interrupts: IE → EI → Router.

        Moved from GraphOrchestrator._route_pathological (Issue #161).
        """
        if "interrupt_evaluator_specialist" in self._specialist_names:
            return "interrupt_evaluator_specialist"
        if CoreSpecialist.EXIT_INTERVIEW.value in self._specialist_names:
            return CoreSpecialist.EXIT_INTERVIEW.value
        return CoreSpecialist.ROUTER.value

    def _build_result(
        self,
        routing_target: str,
        routing_context: str | None,
        diagnostic_text: str,
        diagnostic: dict | None = None,
    ) -> Dict[str, Any]:
        """Build the specialist result with a clean signals snapshot."""
        logger.info(
            f"SignalProcessor: {routing_context or 'NORMAL'} → {routing_target} ({diagnostic_text})"
        )

        snapshot: Dict[str, Any] = {
            "routing_target": routing_target,
            "routing_context": routing_context,
        }
        if diagnostic:
            snapshot["diagnostic"] = diagnostic

        return {"signals": snapshot}
