import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.router_specialist import RouterSpecialist, RouteResponse
from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.enums import CoreSpecialist
from app.src.utils.errors import WorkflowError

class TestRouterParallel:
    @pytest.fixture
    def router(self):
        config = {"llm_config": "test_config"}
        router = RouterSpecialist("router_specialist", config)
        router.set_specialist_map({
            "specialist_a": {"description": "A"},
            "specialist_b": {"description": "B"},
            "specialist_c": {"description": "C"}
        })
        return router

    def test_validate_llm_choice_single(self, router):
        """Test validation of a single specialist choice."""
        valid_options = ["specialist_a", "specialist_b"]
        result = router._validate_llm_choice("specialist_a", valid_options)
        assert result == "specialist_a"

    def test_validate_llm_choice_list(self, router):
        """Test validation of a list of specialist choices."""
        valid_options = ["specialist_a", "specialist_b", "specialist_c"]
        result = router._validate_llm_choice(["specialist_a", "specialist_c"], valid_options)
        assert result == ["specialist_a", "specialist_c"]

    def test_validate_llm_choice_list_partial_invalid(self, router):
        """Test validation filters out invalid choices from a list."""
        valid_options = ["specialist_a", "specialist_b"]
        # specialist_c is invalid
        result = router._validate_llm_choice(["specialist_a", "specialist_c"], valid_options)
        assert result == "specialist_a" # Should return single string if only one valid

    def test_validate_llm_choice_list_all_invalid(self, router):
        """Test fallback when all choices in list are invalid."""
        valid_options = ["specialist_a", "specialist_b"]
        result = router._validate_llm_choice(["invalid_1", "invalid_2"], valid_options)
        assert result == CoreSpecialist.DEFAULT_RESPONDER.value

class TestOrchestratorParallel:
    @pytest.fixture
    def orchestrator(self):
        config = {"workflow": {"max_loop_cycles": 3}}
        specialists = {
            "router_specialist": MagicMock(),
            "specialist_a": MagicMock(),
            "specialist_b": MagicMock()
        }
        allowed_destinations = {"specialist_a", "specialist_b"}
        return GraphOrchestrator(config, specialists, allowed_destinations)

    def test_route_to_next_specialist_list(self, orchestrator):
        """Test routing to a list of specialists."""
        state = {
            "next_specialist": ["specialist_a", "specialist_b"],
            "turn_count": 1
        }
        result = orchestrator.route_to_next_specialist(state)
        assert result == ["specialist_a", "specialist_b"]

    def test_route_to_next_specialist_list_invalid(self, orchestrator):
        """Test routing raises error if any specialist in list is invalid."""
        state = {
            "next_specialist": ["specialist_a", "invalid_specialist"],
            "turn_count": 1
        }
        with pytest.raises(WorkflowError) as excinfo:
            orchestrator.route_to_next_specialist(state)
        assert "Invalid routing destination(s)" in str(excinfo.value)
