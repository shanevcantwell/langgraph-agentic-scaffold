import pytest
from unittest.mock import MagicMock
from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import WorkflowError

class MockSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__("mock_specialist", {})
        self.llm_adapter = MagicMock()

    def _execute_logic(self, state):
        return {"messages": ["success"]}

@pytest.fixture
def orchestrator_with_circuit_breaker():
    config = {
        "workflow": {
            "recursion_limit": 10,
            "max_loop_cycles": 3,
            "stabilization_actions": {
                "structural_integrity_violated": "ROUTE_TO_ERROR_HANDLER"
            }
        }
    }
    specialists = {"mock_specialist": MockSpecialist()}
    return GraphOrchestrator(config, specialists)

def test_circuit_breaker_route_to_error_handler(orchestrator_with_circuit_breaker):
    """
    Test that the circuit breaker catches an invariant violation and triggers
    the configured ROUTE_TO_ERROR_HANDLER action.
    """
    orchestrator = orchestrator_with_circuit_breaker
    specialist = MockSpecialist()
    safe_executor = orchestrator.create_safe_executor(specialist)

    # Create a state that violates structural integrity (missing 'messages')
    # Note: check_state_structure requires 'messages', 'turn_count', 'routing_history', 'scratchpad'
    invalid_state = {
        # "messages": [], # MISSING
        "turn_count": 0,
        "routing_history": [],
        "scratchpad": {},
        "artifacts": {}
    }

    # Execute the specialist
    # Expectation: InvariantMonitor raises CircuitBreakerTriggered -> safe_executor catches it
    # and returns a state update with stabilization_action.
    result = safe_executor(invalid_state)

    # Assertions
    assert "scratchpad" in result
    assert result["scratchpad"]["stabilization_action"] == "ROUTE_TO_ERROR_HANDLER"
    assert "Circuit Breaker Triggered" in result["scratchpad"]["error_report"]
    assert "structural_integrity_violated" in result["scratchpad"]["error_report"]

    # Now verify that the orchestrator respects this action
    # We need to merge the result into the state to simulate graph execution
    invalid_state["scratchpad"].update(result["scratchpad"])
    
    # Check routing
    next_node = orchestrator.route_to_next_specialist(invalid_state)
    assert next_node == "error_handling_specialist"

def test_circuit_breaker_halt_action():
    """
    Test that the circuit breaker halts execution when configured to HALT.
    """
    config = {
        "workflow": {
            "recursion_limit": 10,
            "stabilization_actions": {
                "structural_integrity_violated": "HALT"
            }
        }
    }
    orchestrator = GraphOrchestrator(config, {})
    specialist = MockSpecialist()
    safe_executor = orchestrator.create_safe_executor(specialist)

    invalid_state = {
        # "messages": [], # MISSING
        "turn_count": 0,
        "routing_history": [],
        "scratchpad": {},
        "artifacts": {}
    }

    # Expectation: safe_executor raises WorkflowError (wrapping the CircuitBreakerTriggered/InvariantViolation)
    with pytest.raises(WorkflowError) as excinfo:
        safe_executor(invalid_state)
    
    assert "System Halted by Circuit Breaker" in str(excinfo.value)
