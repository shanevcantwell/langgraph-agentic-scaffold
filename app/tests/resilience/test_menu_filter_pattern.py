"""
Tests for ADR-CORE-016: Menu Filter Pattern (Tier 1 Loop Recovery)

Tests are requirement-based, not implementation-based. We expect some failures initially
as the test suite validates invariant-dependent behavior.
"""

import pytest
from unittest.mock import Mock, patch
from app.src.resilience.monitor import InvariantMonitor
from app.src.graph.state import GraphState
from app.src.utils.errors import CircuitBreakerTriggered, InvariantViolationError


class TestMenuFilterActivation:
    """Test Tier 1 menu filter activation on loop detection."""

    @pytest.fixture
    def monitor(self):
        """Create InvariantMonitor with menu filter enabled."""
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "recursion_limit": 40,
                "enable_menu_filter": True,
                "stabilization_actions": {
                    "loop_detected": "HALT"
                }
            }
        }
        return InvariantMonitor(config)

    @pytest.fixture
    def base_state(self):
        """Create base GraphState without loops."""
        return {
            "messages": [],
            "routing_history": ["triage_architect", "facilitator_specialist"],
            "turn_count": 2,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

    def test_immediate_repetition_loop_activates_menu_filter(self, monitor, base_state):
        """
        REQUIREMENT: Immediate repetition (A→A→A) triggers menu filter.
        EXPECTED: Returns state update with forbidden_specialists = ["A"]
        """
        # Setup: 4 repetitions of same specialist (threshold + 1)
        base_state["routing_history"] = [
            "triage_architect",
            "open_interpreter_specialist",
            "open_interpreter_specialist",
            "open_interpreter_specialist",
            "open_interpreter_specialist"
        ]

        # Execute
        result = monitor.check_invariants(base_state, stage="pre-execution:router")

        # Verify
        assert result is not None, "Should return state update, not None"
        assert "scratchpad" in result
        assert "forbidden_specialists" in result["scratchpad"]
        assert result["scratchpad"]["forbidden_specialists"] == ["open_interpreter_specialist"]
        assert "loop_detection_reason" in result["scratchpad"]
        assert "immediate loop" in result["scratchpad"]["loop_detection_reason"]

    def test_two_step_cycle_loop_forbids_both_specialists(self, monitor, base_state):
        """
        REQUIREMENT: 2-step cycle (A→B→A→B) triggers menu filter and forbids BOTH specialists.
        EXPECTED: Returns state update with forbidden_specialists = ["A", "B"]
        """
        # Setup: 4 complete cycles of [web_builder, systems_architect]
        # That's 8 total entries (4 * 2)
        base_state["routing_history"] = [
            "web_builder", "systems_architect",
            "web_builder", "systems_architect",
            "web_builder", "systems_architect",
            "web_builder", "systems_architect"
        ]

        # Execute
        result = monitor.check_invariants(base_state, stage="pre-execution:router")

        # Verify
        assert result is not None
        assert "scratchpad" in result
        assert "forbidden_specialists" in result["scratchpad"]
        # Should forbid BOTH specialists in the cycle
        forbidden = result["scratchpad"]["forbidden_specialists"]
        assert len(forbidden) == 2
        assert "web_builder" in forbidden
        assert "systems_architect" in forbidden
        assert "2-step cycle" in result["scratchpad"]["loop_detection_reason"]

    def test_below_threshold_does_not_trigger_menu_filter(self, monitor, base_state):
        """
        REQUIREMENT: Below threshold repetitions should not trigger menu filter.
        EXPECTED: Returns None (no violations)
        """
        # Setup: Only 3 repetitions (at threshold, not exceeding)
        base_state["routing_history"] = [
            "triage_architect",
            "file_ops_specialist",
            "file_ops_specialist",
            "file_ops_specialist"
        ]

        # Execute
        result = monitor.check_invariants(base_state, stage="pre-execution:router")

        # Verify: Should not trigger (threshold is 3, this is exactly 3)
        # Note: The invariant detector uses > threshold, so 3 repetitions should NOT trigger
        assert result is None, "Should not trigger menu filter at threshold boundary"

    def test_no_loop_returns_none(self, monitor, base_state):
        """
        REQUIREMENT: No loop detected should return None.
        EXPECTED: Returns None (no state updates)
        """
        # Setup: Normal routing history, no loops
        base_state["routing_history"] = [
            "triage_architect",
            "facilitator_specialist",
            "researcher_specialist",
            "chat_specialist"
        ]

        # Execute
        result = monitor.check_invariants(base_state, stage="pre-execution:router")

        # Verify
        assert result is None


class TestMenuFilterDisabled:
    """Test behavior when menu filter is disabled via config."""

    @pytest.fixture
    def monitor_disabled(self):
        """Create InvariantMonitor with menu filter DISABLED."""
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "recursion_limit": 40,
                "enable_menu_filter": False,  # DISABLED
                "stabilization_actions": {
                    "loop_detected": "HALT"
                }
            }
        }
        return InvariantMonitor(config)

    def test_disabled_menu_filter_triggers_immediate_circuit_breaker(self, monitor_disabled):
        """
        REQUIREMENT: When menu filter disabled, loop detection raises CircuitBreakerTriggered immediately.
        EXPECTED: Raises CircuitBreakerTriggered (no menu filter activation)
        """
        state = {
            "messages": [],
            "routing_history": [
                "router",
                "file_ops_specialist",
                "file_ops_specialist",
                "file_ops_specialist",
                "file_ops_specialist"
            ],
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        # Execute & Verify
        with pytest.raises(CircuitBreakerTriggered) as exc_info:
            monitor_disabled.check_invariants(state, stage="pre-execution:router")

        assert exc_info.value.action == "HALT"
        assert exc_info.value.violation_type == "loop_detected"


class TestTier3Escalation:
    """Test escalation to Tier 3 circuit breaker when menu filter fails."""

    @pytest.fixture
    def monitor(self):
        """Create InvariantMonitor with menu filter enabled."""
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "recursion_limit": 40,
                "enable_menu_filter": True,
                "stabilization_actions": {
                    "loop_detected": "HALT"
                }
            }
        }
        return InvariantMonitor(config)

    def test_menu_filter_already_active_escalates_to_tier3(self, monitor):
        """
        REQUIREMENT: If loop detected while forbidden_specialists already populated, escalate to Tier 3.
        EXPECTED: Raises CircuitBreakerTriggered with violation_type="loop_detected_tier3"
        """
        state = {
            "messages": [],
            "routing_history": [
                "router",
                "file_ops_specialist",
                "file_ops_specialist",
                "file_ops_specialist",
                "file_ops_specialist"
            ],
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {
                "forbidden_specialists": ["file_ops_specialist"],  # Menu filter already active
                "loop_detection_reason": "Previous loop detected"
            },
            "distillation_state": None
        }

        # Execute & Verify
        with pytest.raises(CircuitBreakerTriggered) as exc_info:
            monitor.check_invariants(state, stage="pre-execution:router")

        assert exc_info.value.action == "HALT"
        assert exc_info.value.violation_type == "loop_detected_tier3"
        assert "Loop detected after menu filter applied" in str(exc_info.value.reason)


class TestSpecialistExtractionFromErrors:
    """Test extraction of specialist names from error messages."""

    @pytest.fixture
    def monitor(self):
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "enable_menu_filter": True
            }
        }
        return InvariantMonitor(config)

    def test_extract_from_immediate_loop_error(self, monitor):
        """
        REQUIREMENT: Extract specialist name from immediate repetition error message.
        EXPECTED: Returns ["specialist_name"]
        """
        error_msg = "Detected immediate loop: 'open_interpreter_specialist' repeated 4 times."
        result = monitor._extract_forbidden_specialists_from_error(error_msg)

        assert result == ["open_interpreter_specialist"]

    def test_extract_from_two_step_cycle_error(self, monitor):
        """
        REQUIREMENT: Extract BOTH specialist names from 2-step cycle error message.
        EXPECTED: Returns ["specialist_a", "specialist_b"]
        """
        error_msg = "Detected 2-step cycle loop: ['web_builder', 'systems_architect'] repeated 4 times."
        result = monitor._extract_forbidden_specialists_from_error(error_msg)

        assert len(result) == 2
        assert "web_builder" in result
        assert "systems_architect" in result

    def test_invalid_error_format_returns_empty_list(self, monitor):
        """
        REQUIREMENT: If error message format is invalid, return empty list.
        EXPECTED: Returns [] and logs warning
        """
        error_msg = "Some unrelated error message"
        result = monitor._extract_forbidden_specialists_from_error(error_msg)

        assert result == []

    def test_extraction_failure_triggers_circuit_breaker(self, monitor):
        """
        REQUIREMENT: If specialist extraction fails (empty list), fall through to circuit breaker.
        EXPECTED: Raises CircuitBreakerTriggered
        """
        # Mock the extraction to return empty list
        with patch.object(monitor, '_extract_forbidden_specialists_from_error', return_value=[]):
            state = {
                "messages": [],
                "routing_history": ["router", "a", "a", "a", "a"],
                "turn_count": 4,
                "task_is_complete": False,
                "next_specialist": None,
                "parallel_tasks": [],
                "artifacts": {},
                "scratchpad": {},
                "distillation_state": None
            }

            with pytest.raises(CircuitBreakerTriggered):
                monitor.check_invariants(state, stage="pre-execution:router")


class TestRouterMenuFiltering:
    """Test RouterSpecialist menu filtering behavior."""

    @pytest.fixture
    def mock_router(self):
        """Create mock RouterSpecialist with specialist_map."""
        from app.src.specialists.router_specialist import RouterSpecialist

        router = RouterSpecialist("router_specialist", {"type": "llm"})
        router.specialist_map = {
            "file_ops_specialist": {"description": "File operations"},
            "researcher_specialist": {"description": "Research"},
            "chat_specialist": {"description": "Chat"},
            "web_builder": {"description": "Web builder"},
            "end_specialist": {"description": "End workflow"}
        }
        return router

    def test_no_forbidden_list_returns_full_menu(self, mock_router):
        """
        REQUIREMENT: When no forbidden_specialists in scratchpad, return full specialist map.
        EXPECTED: Returns all specialists
        """
        state = {
            "scratchpad": {}  # No forbidden_specialists
        }

        result = mock_router._get_available_specialists(state)

        assert len(result) == 5
        assert "file_ops_specialist" in result
        assert "researcher_specialist" in result

    def test_forbidden_list_filters_specialists(self, mock_router):
        """
        REQUIREMENT: When forbidden_specialists populated, remove them from returned menu.
        EXPECTED: Forbidden specialist NOT in returned dictionary
        """
        state = {
            "scratchpad": {
                "forbidden_specialists": ["file_ops_specialist"]
            }
        }

        result = mock_router._get_available_specialists(state)

        assert "file_ops_specialist" not in result
        assert "researcher_specialist" in result
        assert "chat_specialist" in result
        assert len(result) == 4  # 5 total - 1 forbidden

    def test_multiple_forbidden_specialists_all_removed(self, mock_router):
        """
        REQUIREMENT: When multiple specialists forbidden, remove ALL of them.
        EXPECTED: All forbidden specialists removed from menu
        """
        state = {
            "scratchpad": {
                "forbidden_specialists": ["file_ops_specialist", "web_builder"]
            }
        }

        result = mock_router._get_available_specialists(state)

        assert "file_ops_specialist" not in result
        assert "web_builder" not in result
        assert "researcher_specialist" in result
        assert "chat_specialist" in result
        assert len(result) == 3  # 5 total - 2 forbidden

    def test_all_specialists_forbidden_returns_end_specialist_fallback(self, mock_router):
        """
        REQUIREMENT: If ALL specialists forbidden, return only end_specialist as fallback.
        EXPECTED: Returns dictionary with only end_specialist
        """
        state = {
            "scratchpad": {
                "forbidden_specialists": [
                    "file_ops_specialist",
                    "researcher_specialist",
                    "chat_specialist",
                    "web_builder",
                    "end_specialist"
                ]
            }
        }

        result = mock_router._get_available_specialists(state)

        # Should return only end_specialist as fallback
        assert len(result) == 1
        assert "end_specialist" in result


class TestLifecycleManagement:
    """Test forbidden list lifecycle (creation and clearance)."""

    def test_forbidden_list_cleared_after_non_router_execution(self):
        """
        REQUIREMENT: Forbidden list cleared after ANY successful specialist execution (non-router).
        EXPECTED: scratchpad.forbidden_specialists set to None
        """
        # This will be tested via GraphOrchestrator integration test
        # Placeholder to document requirement
        pass

    def test_router_execution_does_not_clear_forbidden_list(self):
        """
        REQUIREMENT: Router specialist execution does NOT clear forbidden list.
        EXPECTED: scratchpad.forbidden_specialists remains populated
        """
        # This will be tested via GraphOrchestrator integration test
        # Placeholder to document requirement
        pass


class TestIntegrationScenarios:
    """End-to-end integration tests for menu filter pattern."""

    @pytest.fixture
    def monitor(self):
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "recursion_limit": 40,
                "enable_menu_filter": True,
                "stabilization_actions": {
                    "loop_detected": "HALT"
                }
            }
        }
        return InvariantMonitor(config)

    def test_full_loop_recovery_flow(self, monitor):
        """
        REQUIREMENT: Full flow - Loop detected → Menu filter activates → Alternative selected → Clearance.
        EXPECTED: State updates propagate correctly through workflow
        """
        # Turn 1-4: Loop detected
        state_with_loop = {
            "messages": [],
            "routing_history": [
                "triage_architect",
                "open_interpreter_specialist",
                "open_interpreter_specialist",
                "open_interpreter_specialist",
                "open_interpreter_specialist"
            ],
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        # Step 1: InvariantMonitor detects loop and returns state update
        menu_filter_update = monitor.check_invariants(state_with_loop, stage="pre-execution:router")

        assert menu_filter_update is not None
        assert menu_filter_update["scratchpad"]["forbidden_specialists"] == ["open_interpreter_specialist"]

        # Step 2: State update applied (simulated)
        state_with_loop["scratchpad"].update(menu_filter_update["scratchpad"])

        # Step 3: Router runs with filtered menu (tested separately)
        # Step 4: Alternative specialist executes successfully
        # Step 5: GraphOrchestrator clears forbidden_specialists (tested separately)

    def test_oscillation_recovery_web_builder_systems_architect(self, monitor):
        """
        REQUIREMENT: 2-step oscillation between web_builder and systems_architect.
        EXPECTED: Both specialists forbidden, router forced to pick alternative
        """
        state = {
            "messages": [],
            "routing_history": [
                "router",
                "web_builder",
                "systems_architect",
                "web_builder",
                "systems_architect",
                "web_builder",
                "systems_architect",
                "web_builder",
                "systems_architect"
            ],
            "turn_count": 8,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        # Execute
        result = monitor.check_invariants(state, stage="pre-execution:router")

        # Verify: Both specialists should be forbidden
        assert result is not None
        forbidden = result["scratchpad"]["forbidden_specialists"]
        assert len(forbidden) == 2
        assert "web_builder" in forbidden
        assert "systems_architect" in forbidden


class TestBoundaryConditions:
    """Test exact threshold boundaries for loop detection."""

    @pytest.fixture
    def monitor(self):
        config = {
            "workflow": {
                "max_loop_cycles": 3,  # Threshold
                "enable_menu_filter": True
            }
        }
        return InvariantMonitor(config)

    def test_exactly_threshold_repetitions(self, monitor):
        """
        REQUIREMENT: Exactly threshold repetitions (not exceeding) should NOT trigger.
        EXPECTED: Returns None
        """
        state = {
            "messages": [],
            "routing_history": ["router", "a", "a", "a"],  # Exactly 3 repetitions
            "turn_count": 3,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        result = monitor.check_invariants(state, stage="pre-execution:router")

        # Should NOT trigger (threshold is boundary, not violation)
        assert result is None

    def test_threshold_plus_one_triggers(self, monitor):
        """
        REQUIREMENT: Threshold + 1 repetitions SHOULD trigger menu filter.
        EXPECTED: Returns state update
        """
        state = {
            "messages": [],
            "routing_history": ["router", "a", "a", "a", "a"],  # 4 repetitions (threshold + 1)
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        result = monitor.check_invariants(state, stage="pre-execution:router")

        assert result is not None
        assert result["scratchpad"]["forbidden_specialists"] == ["a"]


class TestNonLoopInvariants:
    """Test that other invariants (non-loop) still trigger circuit breaker immediately."""

    @pytest.fixture
    def monitor(self):
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "recursion_limit": 10,  # Low limit for testing
                "enable_menu_filter": True,
                "stabilization_actions": {
                    "max_turn_count_exceeded": "HALT",
                    "structural_integrity_violated": "HALT"
                }
            }
        }
        return InvariantMonitor(config)

    def test_max_turn_count_exceeded_triggers_immediate_halt(self, monitor):
        """
        REQUIREMENT: Max turn count violation should trigger circuit breaker immediately (no menu filter).
        EXPECTED: Raises CircuitBreakerTriggered
        """
        state = {
            "messages": [],
            "routing_history": ["a", "b", "c"] * 5,  # 15 turns (exceeds limit of 10)
            "turn_count": 15,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        with pytest.raises(CircuitBreakerTriggered) as exc_info:
            monitor.check_invariants(state, stage="pre-execution:router")

        assert exc_info.value.violation_type == "max_turn_count_exceeded"
        assert exc_info.value.action == "HALT"

    def test_structural_integrity_violation_triggers_immediate_halt(self, monitor):
        """
        REQUIREMENT: Structural integrity violations should trigger circuit breaker immediately.
        EXPECTED: Raises CircuitBreakerTriggered
        """
        # Missing required state key
        incomplete_state = {
            "messages": [],
            # Missing routing_history, turn_count, etc.
        }

        with pytest.raises(CircuitBreakerTriggered) as exc_info:
            monitor.check_invariants(incomplete_state, stage="pre-execution:router")

        assert exc_info.value.violation_type == "structural_integrity_violated"


class TestStateManagement:
    """Test that menu filter state is managed correctly per ADR-CORE-004."""

    def test_forbidden_specialists_in_scratchpad_not_root(self):
        """
        REQUIREMENT: forbidden_specialists must be in scratchpad, NOT root state (ADR-CORE-004).
        EXPECTED: State structure validates correctly
        """
        from app.src.graph.state import Scratchpad

        # Verify Scratchpad model has forbidden_specialists field
        scratchpad = Scratchpad(
            forbidden_specialists=["file_ops_specialist"],
            loop_detection_reason="Test loop detected"
        )

        assert scratchpad.forbidden_specialists == ["file_ops_specialist"]
        assert scratchpad.loop_detection_reason == "Test loop detected"

    def test_scratchpad_merge_semantics(self):
        """
        REQUIREMENT: Scratchpad uses operator.ior reducer (merge semantics).
        EXPECTED: Updates merge correctly
        """
        # This is validated by GraphState TypedDict definition
        # Placeholder to document requirement
        pass


class TestObservability:
    """Test that menu filter actions are logged for observability."""

    @pytest.fixture
    def monitor(self):
        config = {
            "workflow": {
                "max_loop_cycles": 3,
                "enable_menu_filter": True
            }
        }
        return InvariantMonitor(config)

    def test_menu_filter_activation_logged_at_warning_level(self, monitor, caplog):
        """
        REQUIREMENT: Menu filter activation should be logged at WARNING level.
        EXPECTED: Log message contains "TIER 1: Menu Filter"
        """
        import logging
        caplog.set_level(logging.WARNING)

        state = {
            "messages": [],
            "routing_history": ["router", "a", "a", "a", "a"],
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {},
            "distillation_state": None
        }

        monitor.check_invariants(state, stage="pre-execution:router")

        # Verify log message
        assert any("TIER 1: Menu Filter" in record.message for record in caplog.records)

    def test_tier3_escalation_logged_at_error_level(self, monitor, caplog):
        """
        REQUIREMENT: Tier 3 escalation should be logged at ERROR level.
        EXPECTED: Log message contains "TIER 3: Circuit Breaker"
        """
        import logging
        caplog.set_level(logging.ERROR)

        state = {
            "messages": [],
            "routing_history": ["router", "a", "a", "a", "a"],
            "turn_count": 4,
            "task_is_complete": False,
            "next_specialist": None,
            "parallel_tasks": [],
            "artifacts": {},
            "scratchpad": {
                "forbidden_specialists": ["a"]  # Already active
            },
            "distillation_state": None
        }

        with pytest.raises(CircuitBreakerTriggered):
            monitor.check_invariants(state, stage="pre-execution:router")

        # Verify log message
        assert any("TIER 3: Circuit Breaker" in record.message for record in caplog.records)
