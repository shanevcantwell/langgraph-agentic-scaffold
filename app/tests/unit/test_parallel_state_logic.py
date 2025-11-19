import pytest
from app.src.graph.state import reduce_parallel_tasks
from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.enums import CoreSpecialist
from unittest.mock import MagicMock

# --- State Reducer Tests ---

def test_reduce_parallel_tasks_initialization():
    """Test that passing a list REPLACES the current state (Scatter)."""
    current = []
    update = ["task_a", "task_b"]
    result = reduce_parallel_tasks(current, update)
    assert result == ["task_a", "task_b"]

def test_reduce_parallel_tasks_completion():
    """Test that passing a string REMOVES it from the list (Gather)."""
    current = ["task_a", "task_b"]
    update = "task_a"
    result = reduce_parallel_tasks(current, update)
    assert result == ["task_b"]

def test_reduce_parallel_tasks_completion_last_item():
    """Test that removing the last item results in an empty list."""
    current = ["task_b"]
    update = "task_b"
    result = reduce_parallel_tasks(current, update)
    assert result == []

def test_reduce_parallel_tasks_idempotent():
    """Test that removing a non-existent item does nothing."""
    current = ["task_a"]
    update = "task_c"
    result = reduce_parallel_tasks(current, update)
    assert result == ["task_a"]

# --- Orchestrator Barrier Logic Tests ---

@pytest.fixture
def orchestrator():
    config = {"workflow": {"max_loop_cycles": 3}}
    return GraphOrchestrator(config, {})

def test_check_task_completion_barrier_active(orchestrator):
    """Test that workflow terminates (END) if parallel tasks are still pending."""
    state = {
        "task_is_complete": False,
        "parallel_tasks": ["task_b"], # One task remaining
        "routing_history": []
    }
    result = orchestrator.check_task_completion(state)
    # Should return END to pause this branch, waiting for others
    assert result == CoreSpecialist.END.value

def test_check_task_completion_barrier_cleared(orchestrator):
    """Test that workflow proceeds to ROUTER if parallel tasks are empty."""
    state = {
        "task_is_complete": False,
        "parallel_tasks": [], # All tasks done
        "routing_history": []
    }
    result = orchestrator.check_task_completion(state)
    assert result == CoreSpecialist.ROUTER.value

def test_check_task_completion_explicit_complete(orchestrator):
    """Test that explicit task completion overrides barrier (edge case)."""
    state = {
        "task_is_complete": True,
        "parallel_tasks": ["task_b"],
        "routing_history": []
    }
    result = orchestrator.check_task_completion(state)
    assert result == CoreSpecialist.END.value
