# app/tests/unit/test_router_observability.py
"""
Tests for Router observability (Issue #41).

Verifies Router appears in routing_history and produces llm_traces when making LLM calls.
These tests validate the structural changes - integration tests verify actual tracing.
"""
import pytest
from unittest.mock import MagicMock, patch
from langgraph.graph import END
from langchain_core.messages import HumanMessage
from app.src.specialists.router_specialist import RouterSpecialist
from app.src.graph.state_factory import create_test_state


@pytest.fixture
def router_specialist(initialized_specialist_factory):
    """Fixture for an initialized RouterSpecialist."""
    return initialized_specialist_factory("RouterSpecialist")


class TestRouterObservability:
    """Tests for Router observability (Issue #41)."""

    def test_router_appears_in_routing_history(self, router_specialist):
        """Router should add itself to routing_history."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_1"}]
        }

        initial_state = create_test_state(
            messages=[HumanMessage(content="Read a file")],
            turn_count=0
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert
        assert "routing_history" in result
        assert result["routing_history"] == ["router_specialist"]

    def test_router_returns_llm_traces_field(self, router_specialist):
        """Router should return llm_traces field (empty in unit tests due to mock)."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_1"}]
        }

        initial_state = create_test_state(
            messages=[HumanMessage(content="Read a file")],
            turn_count=0
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert: Field exists (actual traces require real adapter)
        assert "llm_traces" in result
        assert isinstance(result["llm_traces"], list)

    def test_router_deterministic_end_path_has_routing_history(self, router_specialist):
        """Deterministic END path (archive exists) should still add Router to routing_history."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })

        # State with archive_report.md - triggers deterministic END path
        initial_state = create_test_state(
            messages=[HumanMessage(content="Complete")],
            turn_count=5,
            artifacts={"archive_report.md": "Workflow report content"}
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert
        assert result["next_specialist"] == END
        assert "routing_history" in result
        assert result["routing_history"] == ["router_specialist"]
        # No LLM call, so no traces
        assert result["llm_traces"] == []

    def test_router_deterministic_dependency_path_has_routing_history(self, router_specialist):
        """Deterministic dependency routing should still add Router to routing_history."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"},
            "research_specialist": {"description": "Research tasks", "tags": []}
        })

        # Single dependency recommendation triggers deterministic path
        initial_state = create_test_state(
            messages=[HumanMessage(content="Need research first")],
            turn_count=1,
            routing_history=["systems_architect"],  # Previous specialist (not planning)
            scratchpad={"recommended_specialists": ["research_specialist"]}
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert
        assert result["next_specialist"] == "research_specialist"
        assert "routing_history" in result
        assert result["routing_history"] == ["router_specialist"]
        # Deterministic path bypasses LLM, so no traces
        assert result["llm_traces"] == []

    def test_router_observability_fields_with_parallel_routing(self, router_specialist):
        """Router observability works correctly with parallel specialist routing."""
        # Arrange
        router_specialist.set_specialist_map({
            "alpha_specialist": {"description": "Alpha"},
            "bravo_specialist": {"description": "Bravo"}
        })
        # LLM returns list for parallel execution
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": ["alpha_specialist", "bravo_specialist"]}, "id": "call_1"}]
        }

        initial_state = create_test_state(
            messages=[HumanMessage(content="Run parallel")],
            turn_count=0
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert
        assert result["next_specialist"] == ["alpha_specialist", "bravo_specialist"]
        assert result["routing_history"] == ["router_specialist"]
        assert "llm_traces" in result

    def test_router_routing_history_is_additive_list(self, router_specialist):
        """Router returns routing_history as list for operator.add reducer."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_1"}]
        }

        # State already has routing history
        initial_state = create_test_state(
            messages=[HumanMessage(content="Read a file")],
            turn_count=2,
            routing_history=["triage_architect", "facilitator_specialist"]
        )

        # Act
        result = router_specialist._execute_logic(initial_state)

        # Assert: Returns list (not modifying existing, will be appended by reducer)
        assert result["routing_history"] == ["router_specialist"]
        # The full history would be ["triage_architect", "facilitator_specialist", "router_specialist"]
        # after the reducer applies operator.add


class TestRouterTracingIntegration:
    """Tests that verify tracing functions are called correctly."""

    def test_tracing_context_is_set_and_cleared(self, router_specialist):
        """Verify set_current_specialist and clear_current_specialist are called."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_1"}]
        }

        initial_state = create_test_state(
            messages=[HumanMessage(content="Read a file")],
            turn_count=0
        )

        # Act & Assert
        with patch('app.src.specialists.router_specialist.set_current_specialist') as mock_set, \
             patch('app.src.specialists.router_specialist.clear_current_specialist') as mock_clear, \
             patch('app.src.specialists.router_specialist.flush_adapter_traces') as mock_flush:

            mock_flush.return_value = []  # No traces from mock

            result = router_specialist._execute_logic(initial_state)

            # Verify tracing context lifecycle
            mock_set.assert_called_once_with("router_specialist")
            mock_clear.assert_called_once()
            mock_flush.assert_called_once()

    def test_turn_trace_built_when_adapter_traces_exist(self, router_specialist):
        """Verify build_specialist_turn_trace is called when adapter captures traces."""
        # Arrange
        router_specialist.set_specialist_map({
            "file_specialist": {"description": "File operations"}
        })
        router_specialist.llm_adapter.invoke.return_value = {
            "tool_calls": [{"args": {"next_specialist": "file_specialist"}, "id": "call_1"}]
        }

        initial_state = create_test_state(
            messages=[HumanMessage(content="Read a file")],
            turn_count=0,
            routing_history=["triage_architect"]
        )

        # Create a mock adapter trace
        from app.src.llm.tracing import AdapterTrace
        mock_trace = AdapterTrace(
            latency_ms=100,
            model_id="test-model",
            response_type="tool_call",
            tool_calls=[{"name": "Route", "args": {"next_specialist": "file_specialist"}}]
        )

        # Act & Assert
        with patch('app.src.specialists.router_specialist.flush_adapter_traces') as mock_flush, \
             patch('app.src.specialists.router_specialist.build_specialist_turn_trace') as mock_build:

            mock_flush.return_value = [mock_trace]
            mock_build.return_value = MagicMock(model_dump=lambda: {"step": 1, "specialist": "router_specialist"})

            result = router_specialist._execute_logic(initial_state)

            # Verify trace was built
            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args[1]
            assert call_kwargs["specialist_name"] == "router_specialist"
            assert call_kwargs["specialist_type"] == "llm"
            assert call_kwargs["from_source"] == "triage_architect"
            assert call_kwargs["step"] == 1  # len(["triage_architect"])

            # Verify trace is in result
            assert len(result["llm_traces"]) == 1
