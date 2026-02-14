# app/tests/unit/test_workflow_runner.py
import pytest
from unittest.mock import MagicMock
import json
from app.src.utils.errors import WorkflowError
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
    runner.app.invoke.assert_called_once() # The runner returns the full state now
    assert result == {"artifacts": {"final_user_response.md": "Workflow complete"}}

def test_workflow_runner_run_sync_handles_missing_artifact(mock_graph_builder):
    """Tests that the sync run method handles a missing final artifact gracefully."""
    # Arrange
    runner = WorkflowRunner()
    # Override the mock to return a state without the expected artifact
    runner.app.invoke.return_value = {"artifacts": {"some_other_artifact.txt": "some data"}}

    # Act
    result = runner.run("Test goal")

    # Assert
    assert result == {"artifacts": {"some_other_artifact.txt": "some data"}}

def test_workflow_runner_run_sync_handles_invoke_error(mock_graph_builder):
    """Tests that the sync run method raises a WorkflowError on graph invocation failure."""
    # Arrange
    runner = WorkflowRunner()
    runner.app.invoke.side_effect = Exception("Graph failed!")

    # Act
    result = runner.run("Test goal")

    # Assert
    assert "error" in result # The runner now returns a dict with an error key
    assert "Workflow failed catastrophically: Graph failed!" in result["error"]

@pytest.mark.asyncio
async def test_workflow_runner_run_streaming_handles_astream_error(mock_graph_builder):
    """Tests that the streaming run method yields an error on graph stream failure."""
    # Arrange
    runner = WorkflowRunner()
    runner.app.astream.side_effect = Exception("Stream failed!")

    # Act & Assert
    error_message_found = False
    async for item in runner.run_streaming("Test goal"):
        if "error_report" in item and "error" in item["error_report"]:
            error_message_found = True
            assert "Stream failed!" in item["error_report"]["error"]
            break
    assert error_message_found

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
    
    # The runner now yields the raw events from LangGraph's astream.
    # The mock generator yields two events, plus run_id and conversation_id metadata events.
    assert len(streamed_results) == 4
    assert "run_id" in streamed_results[0]
    assert "conversation_id" in streamed_results[1]
    assert "node1" in streamed_results[2]
    assert "node2" in streamed_results[3]
    assert "final_user_response.md" in streamed_results[3]["node2"]["artifacts"]