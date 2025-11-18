import pytest
import time
from unittest.mock import MagicMock
from langgraph.graph import StateGraph, END
from app.src.graph.state import GraphState
from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.base import BaseSpecialist

class MockSpecialist(BaseSpecialist):
    def __init__(self, name, delay=0.0):
        super().__init__(name, {})
        self.delay = delay
        self.execution_time = None

    def _execute_logic(self, state):
        if self.delay:
            time.sleep(self.delay)
        self.execution_time = time.time()
        return {"routing_history": [self.specialist_name]}

@pytest.mark.asyncio
async def test_parallel_execution_fan_out():
    """
    Verifies that the graph executes nodes in parallel when the router returns a list.
    Task 3.2 Definition of Done.
    """
    # 1. Setup Mocks
    mock_a = MockSpecialist("mock_a", delay=0.5)
    mock_b = MockSpecialist("mock_b", delay=0.5)
    
    # Mock Router that returns a list
    def mock_router_execute(state):
        return {"next_specialist": ["mock_a", "mock_b"], "turn_count": state.get("turn_count", 0) + 1}

    # 2. Setup Orchestrator
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {
        "router": MagicMock(),
        "mock_a": mock_a,
        "mock_b": mock_b
    }
    allowed_destinations = {"mock_a", "mock_b"}
    orchestrator = GraphOrchestrator(config, specialists, allowed_destinations)

    # 3. Build Graph Manually (mimicking GraphBuilder)
    workflow = StateGraph(GraphState)
    
    workflow.add_node("router", mock_router_execute)
    workflow.add_node("mock_a", mock_a.execute)
    workflow.add_node("mock_b", mock_b.execute)
    
    # Add conditional edge from router
    workflow.add_conditional_edges(
        "router",
        orchestrator.route_to_next_specialist,
        {"mock_a": "mock_a", "mock_b": "mock_b", END: END}
    )
    
    # Add edges back to END (to keep test simple)
    workflow.add_edge("mock_a", END)
    workflow.add_edge("mock_b", END)
    
    workflow.set_entry_point("router")
    app = workflow.compile()

    # 4. Execute
    initial_state = {
        "messages": [],
        "turn_count": 0,
        "routing_history": []
    }
    
    start_time = time.time()
    # Use ainvoke for async execution (required for parallel)
    result = await app.ainvoke(initial_state)
    end_time = time.time()
    
    # 5. Assertions
    
    # Verify both executed
    assert mock_a.execution_time is not None
    assert mock_b.execution_time is not None
    
    # Verify total time is close to max(delay_a, delay_b) rather than sum
    # 0.5s + 0.5s = 1.0s (serial) vs ~0.5s (parallel)
    duration = end_time - start_time
    print(f"Execution duration: {duration:.4f}s")
    
    # Assert parallel execution (allow some overhead, e.g., 0.8s is still faster than 1.0s serial)
    assert duration < 0.9, f"Execution took {duration:.4f}s, expected < 0.9s (parallel)"
    
    # Verify routing history contains both (order is non-deterministic in parallel)
    # Note: LangGraph merges updates. 
    # If both return routing_history, one might overwrite the other or they merge?
    # In our GraphOrchestrator.safe_executor, we handle this, but here we use raw execute.
    # Let's check the result keys.
    
    # Check that the final state reflects execution of both
    # (This depends on how LangGraph merges state updates from parallel nodes)
    # For this test, we just care that they RAN.
