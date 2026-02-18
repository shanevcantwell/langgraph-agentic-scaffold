"""
Tests for SignalProcessorSpecialist (ADR-077: Signal Processor Architecture).

Replaces test_interrupt_classifier.py. The signal processor is a procedural specialist
(no LLM) that reads routing signals and determines the next graph destination.

Priority chain:
1. stabilization_action in signals (circuit breaker) → EI/END
2. user_abort in scratchpad (externally set)          → END
3. max_iterations_exceeded in signals (PD)            → EI  (benign_continuation)
4. stagnation_detected in signals (PD)                → IE/EI/Router (stagnation)
5. artifacts present                                  → EI  (normal)
6. No artifacts, no signals                           → Router (normal)
"""

import pytest
from unittest.mock import MagicMock

from app.src.specialists.signal_processor_specialist import SignalProcessorSpecialist
from app.src.enums import CoreSpecialist
from app.src.graph.state import reduce_signals
from app.src.workflow.graph_orchestrator import GraphOrchestrator


@pytest.fixture
def signal_processor():
    """Create a SignalProcessorSpecialist with a realistic specialist map."""
    config = {"type": "procedural"}
    sp = SignalProcessorSpecialist("signal_processor_specialist", config)
    sp.set_specialist_map({
        "interrupt_evaluator_specialist": MagicMock(),
        "facilitator_specialist": MagicMock(),
        CoreSpecialist.EXIT_INTERVIEW.value: MagicMock(),
        CoreSpecialist.END.value: MagicMock(),
        CoreSpecialist.ROUTER.value: MagicMock(),
    })
    return sp


# =============================================================================
# Priority 1: Circuit breaker stabilization
# =============================================================================

class TestSignalProcessorCircuitBreaker:
    """Tests for stabilization_action (circuit breaker) signal handling."""

    def test_stabilization_action_routes_to_exit_interview(self, signal_processor):
        """CB ROUTE_TO_ERROR_HANDLER → EI when EI is available."""
        state = {
            "signals": {"stabilization_action": "ROUTE_TO_ERROR_HANDLER"},
            "scratchpad": {},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value
        assert result["signals"]["routing_context"] == "circuit_breaker"

    def test_stabilization_action_falls_back_to_end(self):
        """CB routes to END when EI is not available."""
        config = {"type": "procedural"}
        sp = SignalProcessorSpecialist("signal_processor_specialist", config)
        sp.set_specialist_map({
            CoreSpecialist.END.value: MagicMock(),
            CoreSpecialist.ROUTER.value: MagicMock(),
        })

        state = {
            "signals": {"stabilization_action": "ROUTE_TO_ERROR_HANDLER"},
            "scratchpad": {},
            "artifacts": {},
        }

        result = sp._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.END.value


# =============================================================================
# Priority 2: User abort (terminal)
# =============================================================================

class TestSignalProcessorTerminal:
    """Tests for TERMINAL (user_abort) signal handling."""

    def test_user_abort_routes_to_end(self, signal_processor):
        """TERMINAL: user_abort in scratchpad → END."""
        state = {
            "signals": {},
            "scratchpad": {"user_abort": True},
            "artifacts": {"some_work": "partial"},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.END.value
        assert result["signals"]["routing_context"] == "user_abort"

    def test_user_abort_takes_priority_over_max_iterations(self, signal_processor):
        """TERMINAL takes priority over BENIGN."""
        state = {
            "signals": {"max_iterations_exceeded": True},
            "scratchpad": {"user_abort": True},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.END.value


# =============================================================================
# Priority 3: BENIGN — max iterations exceeded
# =============================================================================

class TestSignalProcessorBenign:
    """Tests for BENIGN (max_iterations_exceeded) signal handling."""

    def test_max_iterations_exceeded_routes_to_exit_interview(self, signal_processor):
        """BENIGN: max_iterations_exceeded → EI with benign_continuation context."""
        state = {
            "signals": {"max_iterations_exceeded": True},
            "scratchpad": {},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value
        assert result["signals"]["routing_context"] == "benign_continuation"

    def test_benign_takes_priority_over_stagnation(self, signal_processor):
        """BENIGN (max_iterations) takes priority over PATHOLOGICAL (stagnation)."""
        state = {
            "signals": {
                "max_iterations_exceeded": True,
                "stagnation_detected": True,
            },
            "scratchpad": {},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value
        assert result["signals"]["routing_context"] == "benign_continuation"

    def test_benign_takes_priority_over_artifacts(self, signal_processor):
        """BENIGN takes priority over normal artifact flow."""
        state = {
            "signals": {"max_iterations_exceeded": True},
            "scratchpad": {},
            "artifacts": {"some_work": "partial results"},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value
        assert result["signals"]["routing_context"] == "benign_continuation"


# =============================================================================
# Priority 4: PATHOLOGICAL — stagnation detected
# =============================================================================

class TestSignalProcessorPathological:
    """Tests for PATHOLOGICAL (stagnation) signal handling."""

    def test_stagnation_detected_routes_to_interrupt_evaluator(self, signal_processor):
        """PATHOLOGICAL: stagnation_detected → IE when available."""
        state = {
            "signals": {
                "stagnation_detected": True,
                "stagnation_tool": "read_file",
                "stagnation_args": {"path": "/x"},
            },
            "scratchpad": {},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == "interrupt_evaluator_specialist"
        assert result["signals"]["routing_context"] == "stagnation"
        assert result["signals"]["diagnostic"]["stagnation_tool"] == "read_file"
        assert result["signals"]["diagnostic"]["stagnation_args"] == {"path": "/x"}

    def test_stagnation_falls_back_to_exit_interview(self):
        """PATHOLOGICAL fallback: IE unavailable → EI."""
        config = {"type": "procedural"}
        sp = SignalProcessorSpecialist("signal_processor_specialist", config)
        sp.set_specialist_map({
            CoreSpecialist.EXIT_INTERVIEW.value: MagicMock(),
            CoreSpecialist.END.value: MagicMock(),
            CoreSpecialist.ROUTER.value: MagicMock(),
        })

        state = {
            "signals": {"stagnation_detected": True},
            "scratchpad": {},
            "artifacts": {},
        }

        result = sp._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value

    def test_stagnation_falls_back_to_router(self):
        """PATHOLOGICAL fallback: IE and EI unavailable → Router."""
        config = {"type": "procedural"}
        sp = SignalProcessorSpecialist("signal_processor_specialist", config)
        sp.set_specialist_map({
            CoreSpecialist.END.value: MagicMock(),
            CoreSpecialist.ROUTER.value: MagicMock(),
        })

        state = {
            "signals": {"stagnation_detected": True},
            "scratchpad": {},
            "artifacts": {},
        }

        result = sp._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.ROUTER.value


# =============================================================================
# Priority 5-6: Normal flow
# =============================================================================

class TestSignalProcessorNormalFlow:
    """Tests for normal flow (no interrupt signals)."""

    def test_artifacts_present_routes_to_exit_interview(self, signal_processor):
        """NORMAL: artifacts present → EI for semantic completion check."""
        state = {
            "signals": {},
            "scratchpad": {},
            "artifacts": {"report.md": "Some analysis results"},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.EXIT_INTERVIEW.value
        assert result["signals"]["routing_context"] is None

    def test_no_artifacts_no_signals_routes_to_router(self, signal_processor):
        """NORMAL: no artifacts, no signals → Router (continue workflow)."""
        state = {
            "signals": {},
            "scratchpad": {},
            "artifacts": {},
        }

        result = signal_processor._execute_logic(state)

        assert result["signals"]["routing_target"] == CoreSpecialist.ROUTER.value
        assert result["signals"]["routing_context"] is None


# =============================================================================
# reduce_signals reducer
# =============================================================================

class TestReduceSignals:
    """Tests for the replace reducer on the signals field."""

    def test_replace_reducer_replaces_entirely(self):
        """New signals dict replaces old — no merge."""
        current = {"stagnation_detected": True, "stagnation_tool": "read_file"}
        update = {"routing_target": "exit_interview_specialist"}

        result = reduce_signals(current, update)

        assert result == {"routing_target": "exit_interview_specialist"}
        assert "stagnation_detected" not in result

    def test_replace_reducer_preserves_on_none(self):
        """None update preserves current state (node didn't write signals)."""
        current = {"routing_target": "router_specialist"}

        result = reduce_signals(current, None)

        assert result == {"routing_target": "router_specialist"}

    def test_replace_reducer_empty_dict_clears(self):
        """Empty dict update clears all signals."""
        current = {"stagnation_detected": True}

        result = reduce_signals(current, {})

        assert result == {}


# =============================================================================
# route_from_signal edge function
# =============================================================================

class TestRouteFromSignal:
    """Tests for the trivial edge function on GraphOrchestrator."""

    def test_route_from_signal_reads_routing_target(self):
        """Edge function returns whatever routing_target the signal processor set."""
        config = {"workflow": {"max_loop_cycles": 3}}
        specialists = {CoreSpecialist.ROUTER.value: MagicMock()}
        orch = GraphOrchestrator(config, specialists)

        state = {"signals": {"routing_target": "exit_interview_specialist"}}

        assert orch.route_from_signal(state) == "exit_interview_specialist"

    def test_route_from_signal_falls_back_to_router(self):
        """Missing routing_target falls back to Router."""
        config = {"workflow": {"max_loop_cycles": 3}}
        specialists = {CoreSpecialist.ROUTER.value: MagicMock()}
        orch = GraphOrchestrator(config, specialists)

        state = {"signals": {}}

        assert orch.route_from_signal(state) == CoreSpecialist.ROUTER.value
