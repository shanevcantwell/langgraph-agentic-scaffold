# Audit Date: Sept 23, 2025
# app/tests/unit/test_workflow_runner.py
import pytest
from unittest.mock import MagicMock

from app.src.workflow.runner import WorkflowRunner

@pytest.fixture
def mock_graph_builder(mocker):
    """Mocks the GraphBuilder and its dependencies to isolate the WorkflowRunner."""
    mock_app = MagicMock()
    mock_app.invoke.return_value = {"artifacts": {"final_user_response.md": "Workflow complete"}}
    
    # For async streaming, we need an AsyncMock and an async generator
    async def mock_astream_gen():
        yield {"node1": {"messages": ["Entering node 1"]}}
        yield {"node2": {"messages": ["Finished node 2"], "artifacts": {"final_user_response.md": "Final streaming response"}}}

    mock_app.astream = MagicMock(return_value=mock_astream_gen())

    mock_builder_instance = MagicMock()
    mock_builder_instance.build.return_value = mock_app
    mock_builder_instance.config = {
        "workflow": {"recursion_limit": 25},
        "llm_providers": {},
        "specialists": {}
    }
    mock_builder_instance.specialists = {}

    mocker.patch('app.src.workflow.runner.GraphBuilder', return_value=mock_builder_instance)
    return mock_builder_instance

def test_workflow_runner_init(mock_graph_builder):
    """Tests that the WorkflowRunner initializes correctly."""
    # Act
    runner = WorkflowRunner()

    # Assert
    mock_graph_builder.build.assert_called_once()
    assert runner.app is not None
    assert runner.recursion_limit == 25

def test_workflow_runner_run_sync(mock_graph_builder):
    """Tests the synchronous run method."""
    # Arrange
    runner = WorkflowRunner()
    goal = "Test synchronous execution"

    # Act
    result = runner.run(goal)

    # Assert
    runner.app.invoke.assert_called_once()
    assert result == {"final_user_response": "Workflow complete"}

@pytest.mark.asyncio
async def test_workflow_runner_run_streaming(mock_graph_builder):
    """Tests the asynchronous streaming method."""
    # Arrange
    runner = WorkflowRunner()
    goal = "Test streaming execution"

    # Act
    streamed_results = [item async for item in runner.run_streaming(goal)]

    # Assert
    runner.app.astream.assert_called_once()
    
    # Check the yielded log messages and final state
    assert len(streamed_results) == 3
    assert "Finished node: node1" in streamed_results[0]
    assert "Finished node: node2" in streamed_results[1]

    # Check that the final state is yielded correctly
    final_state_message = streamed_results[-1]
    assert final_state_message.startswith("FINAL_STATE::")
    assert '"final_user_response.md": "Final streaming response"' in final_state_message