import pytest
from unittest.mock import MagicMock, patch
from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.graph.state_factory import create_test_state
from app.src.specialists.base import BaseSpecialist

class MockSpecialist(BaseSpecialist):
    def _execute_logic(self, state):
        return {"artifacts": {"test": "done"}}

def test_invariant_monitor_called_during_execution():
    """
    Verifies that the InvariantMonitor is invoked during the execution lifecycle.
    Task 1.5 Definition of Done.
    """
    # Setup
    config = {"workflow": {"recursion_limit": 10, "max_loop_cycles": 3}}
    specialists = {"mock_specialist": MockSpecialist("mock_specialist", {})}
    
    # Patch InvariantMonitor where it is imported in graph_orchestrator
    with patch("app.src.workflow.graph_orchestrator.InvariantMonitor") as MockMonitorClass:
        mock_monitor_instance = MockMonitorClass.return_value
        
        orchestrator = GraphOrchestrator(config, specialists)
        
        # Create safe executor
        safe_exec = orchestrator.create_safe_executor(specialists["mock_specialist"])
        
        # Execute
        state = create_test_state(turn_count=1)
        safe_exec(state)
        
        # Assert check_invariants was called
        mock_monitor_instance.check_invariants.assert_called_once()
        call_args = mock_monitor_instance.check_invariants.call_args
        
        # Verify arguments
        # Note: safe_executor modifies state in place or passes it through? 
        # It receives state.
        assert call_args[0][0] == state # First arg is state
        assert "pre-execution:mock_specialist" in call_args[1]["stage"]
