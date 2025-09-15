# app/tests/unit/test_workflow_runner.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.src.workflow.runner import WorkflowRunner
from app.src.graph.state import GraphState

@pytest.fixture
def mock_chief_of_staff(mocker):
    """Mocks the ChiefOfStaff and its dependencies to isolate the WorkflowRunner."""
    mock_app = MagicMock()
    mock_app.invoke.return_value = {"messages": ["Workflow complete"]}
    
    # For async streaming, we need an AsyncMock and an async generator
    async def mock_astream_gen():
        yield {"node1": {"messages": ["Entering node 1"]}}
        yield {"node2": {"messages": ["Finished node 2"]}}

    mock_app.astream = MagicMock(return_value=mock_astream_gen())

    mock_cos_instance = MagicMock()
    mock_cos_instance.get_graph.return_value = mock_app
    mock_cos_instance.config = {
        "workflow": {"recursion_limit": 25},
        "llm_providers": {},
        "specialists": {}
    }

    mocker.patch('app.src.workflow.runner.ChiefOfStaff', return_value=mock_cos_instance)
    return mock_cos_instance

def test_workflow_runner_init(mock_chief_of_staff):
    """Tests that the WorkflowRunner initializes correctly."""
    # Act
    runner = WorkflowRunner()

    # Assert
    mock_chief_of_staff.get_graph.assert_called_once()
    assert runner.app is not None
    assert runner.recursion_limit == 25

def test_workflow_runner_run_sync(mock_chief_of_staff):
    """Tests the synchronous run method."""
    # Arrange
    runner = WorkflowRunner()
    goal = "Test synchronous execution"

    # Act
    result = runner.run(goal)

    # Assert
    runner.app.invoke.assert_called_once()
    assert result == {"messages": ["Workflow complete"]}

@pytest.mark.asyncio
async def test_workflow_runner_run_streaming(mock_chief_of_staff):
    """Tests the asynchronous streaming method."""
    # Arrange
    runner = WorkflowRunner()
    goal = "Test streaming execution"

    # Act
    streamed_results = [item async for item in runner.run_streaming(goal)]

    # Assert
    runner.app.astream.assert_called_once()
    
    # Check the yielded log messages
    assert len(streamed_results) == 2
    assert "Finished node: node1" in streamed_results[0]
    assert "Finished node: node2" in streamed_results[1]

    # Check that the final state is yielded correctly
    final_state_message = streamed_results[-1]
    assert final_state_message.startswith("FINAL_STATE::")
    # The mock doesn't produce a real final state, so we just check the prefix