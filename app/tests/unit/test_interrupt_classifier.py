"""
Tests for the Interrupt Classifier (ADR-CORE-061: Tiered Interrupt Architecture).

These tests define the EXPECTED behavior of classify_interrupt() BEFORE implementation.
They will FAIL until the implementation is complete - this is intentional (test-first).

The Interrupt Classifier is Tier 1 of the interrupt architecture:
- BENIGN interrupts:
  - max_iterations_exceeded → Exit Interview (for feedback, then facilitator via after_exit_interview)
  - context_overflow → Facilitator (compress and continue)
- TERMINAL interrupts → End (immediate termination)
- PATHOLOGICAL interrupts → Interrupt Evaluator (needs LLM judgment)
- Normal flow + artifacts → Exit Interview (semantic completion)
- Normal flow, no artifacts → Router (continue workflow)

Note: max_iterations routes through EI to provide "INCOMPLETE" feedback that router
needs to continue the loop (see #139 BENIGN continuation fix).
"""

import pytest
from unittest.mock import MagicMock, patch

from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.enums import CoreSpecialist


@pytest.fixture
def orchestrator():
    """Create a GraphOrchestrator instance for testing.

    Issue #161: Specialists dict must include specialists that classify_interrupt
    routes to, since routing functions now guard with `in self.specialists` checks.
    """
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {
        "interrupt_evaluator_specialist": MagicMock(),
        "facilitator_specialist": MagicMock(),
        CoreSpecialist.EXIT_INTERVIEW.value: MagicMock(),
        CoreSpecialist.END.value: MagicMock(),
        CoreSpecialist.ROUTER.value: MagicMock(),
    }
    orch = GraphOrchestrator(config, specialists)
    # Mock the external_mcp_client for stutter detection
    orch.external_mcp_client = MagicMock()
    return orch


class TestClassifyInterruptBenign:
    """Tests for BENIGN interrupt classification."""

    def test_max_iterations_exceeded_in_scratchpad_routes_to_exit_interview(self, orchestrator):
        """BENIGN: max_iterations_exceeded flag → Exit Interview for feedback.

        EI provides the "INCOMPLETE" signal that router needs to continue the loop.
        Flow: EI → after_exit_interview → facilitator → router → back to specialist
        """
        state = {
            "scratchpad": {"max_iterations_exceeded": True},
            "artifacts": {},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.EXIT_INTERVIEW.value, \
            "max_iterations_exceeded should route to Exit Interview for feedback"

    def test_max_iterations_exceeded_in_artifacts_routes_to_exit_interview(self, orchestrator):
        """BENIGN: max_iterations_exceeded in artifacts → Exit Interview."""
        state = {
            "scratchpad": {},
            "artifacts": {"max_iterations_exceeded": True},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.EXIT_INTERVIEW.value, \
            "max_iterations_exceeded in artifacts should route to Exit Interview"

    def test_context_overflow_routes_to_facilitator(self, orchestrator):
        """BENIGN: context_overflow → Facilitator (compress and continue)."""
        state = {
            "scratchpad": {"context_overflow": True},
            "artifacts": {},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == "facilitator_specialist", \
            "context_overflow should route to Facilitator (BENIGN - compress and continue)"


class TestClassifyInterruptTerminal:
    """Tests for TERMINAL interrupt classification (immediate end)."""

    def test_user_abort_routes_to_end(self, orchestrator):
        """TERMINAL: user_abort → End (immediate termination)."""
        state = {
            "scratchpad": {"user_abort": True},
            "artifacts": {"some_work": "partial"},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.END.value, \
            "user_abort should route to End (TERMINAL)"


class TestClassifyInterruptPathological:
    """Tests for PATHOLOGICAL interrupt classification (needs LLM judgment)."""

    def test_stagnation_detected_flag_routes_to_interrupt_evaluator(self, orchestrator):
        """PATHOLOGICAL: stagnation_detected flag → Interrupt Evaluator."""
        state = {
            "scratchpad": {"stagnation_detected": True},
            "artifacts": {},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == "interrupt_evaluator_specialist", \
            "stagnation_detected should route to Interrupt Evaluator (PATHOLOGICAL)"

    def test_tool_error_routes_to_interrupt_evaluator(self, orchestrator):
        """PATHOLOGICAL: tool_error flag → Interrupt Evaluator."""
        state = {
            "scratchpad": {"tool_error": True},
            "artifacts": {},
            "routing_history": ["some_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == "interrupt_evaluator_specialist", \
            "tool_error should route to Interrupt Evaluator (PATHOLOGICAL)"

    def test_trace_stutter_detected_routes_to_interrupt_evaluator(self, orchestrator):
        """PATHOLOGICAL: trace stutter (via semantic-chunker drift) → Interrupt Evaluator."""
        # Simulate two nearly-identical traces (low drift = stutter)
        state = {
            "scratchpad": {},
            "artifacts": {
                "research_trace_0": [{"tool": "read_file", "args": {"path": "/foo"}}],
                "research_trace_1": [{"tool": "read_file", "args": {"path": "/foo"}}],  # Same!
            },
            "routing_history": ["project_director", "project_director"],
        }

        # Mock semantic-chunker to return low drift (stutter)
        orchestrator.external_mcp_client = MagicMock()
        with patch.object(orchestrator, '_detect_trace_stutter', return_value=True):
            result = orchestrator.classify_interrupt(state)

        assert result == "interrupt_evaluator_specialist", \
            "Trace stutter should route to Interrupt Evaluator (PATHOLOGICAL)"

    def test_unrecovered_failure_routes_to_interrupt_evaluator(self, orchestrator):
        """PATHOLOGICAL: unrecovered tool failure in trace → Interrupt Evaluator."""
        state = {
            "scratchpad": {},
            "artifacts": {
                "research_trace_0": [
                    {"tool": "read_file", "success": True},
                    {"tool": "move_file", "success": False, "error": "Permission denied"},
                    # No successful ops after failure
                ],
            },
            "routing_history": ["project_director"],
        }

        with patch.object(orchestrator, '_detect_unrecovered_failures', return_value=True):
            result = orchestrator.classify_interrupt(state)

        assert result == "interrupt_evaluator_specialist", \
            "Unrecovered failure should route to Interrupt Evaluator (PATHOLOGICAL)"


class TestClassifyInterruptNormalFlow:
    """Tests for normal flow (no interrupts)."""

    def test_artifacts_present_routes_to_exit_interview(self, orchestrator):
        """NORMAL: artifacts present → Exit Interview for semantic completion."""
        state = {
            "scratchpad": {},
            "artifacts": {"report.md": "Some analysis results"},
            "routing_history": ["text_analysis_specialist"],
        }

        # Ensure no pathological detection triggers
        with patch.object(orchestrator, '_detect_trace_stutter', return_value=False):
            with patch.object(orchestrator, '_detect_unrecovered_failures', return_value=False):
                result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.EXIT_INTERVIEW.value, \
            "Artifacts present should route to Exit Interview (semantic completion)"

    def test_no_artifacts_no_flags_routes_to_router(self, orchestrator):
        """NORMAL: no artifacts, no flags → Router (continue workflow)."""
        state = {
            "scratchpad": {},
            "artifacts": {},
            "routing_history": ["facilitator_specialist"],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.ROUTER.value, \
            "No artifacts, no flags should route to Router (continue workflow)"


class TestClassifyInterruptPriorityOrder:
    """Tests for correct priority ordering of interrupt classification."""

    def test_terminal_takes_priority_over_benign(self, orchestrator):
        """TERMINAL should take priority over BENIGN flags."""
        state = {
            "scratchpad": {
                "user_abort": True,
                "max_iterations_exceeded": True,  # Would normally be BENIGN
            },
            "artifacts": {},
            "routing_history": [],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.END.value, \
            "TERMINAL (user_abort) should take priority over BENIGN (max_iterations)"

    def test_benign_takes_priority_over_pathological(self, orchestrator):
        """BENIGN (max_iterations) should take priority over PATHOLOGICAL detection."""
        state = {
            "scratchpad": {
                "max_iterations_exceeded": True,  # BENIGN → EI
                "stagnation_detected": True,  # Would be PATHOLOGICAL
            },
            "artifacts": {},
            "routing_history": [],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.EXIT_INTERVIEW.value, \
            "BENIGN (max_iterations) should take priority over PATHOLOGICAL"

    def test_benign_takes_priority_over_artifacts(self, orchestrator):
        """BENIGN interrupt (max_iterations) should route to EI even if artifacts present."""
        state = {
            "scratchpad": {"max_iterations_exceeded": True},
            "artifacts": {"some_work": "partial results"},
            "routing_history": [],
        }

        result = orchestrator.classify_interrupt(state)

        assert result == CoreSpecialist.EXIT_INTERVIEW.value, \
            "BENIGN interrupt should take priority over normal artifact flow"
