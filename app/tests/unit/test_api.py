# Audit Date: Sept 23, 2025
# app/tests/unit/test_api.py
import pytest
from app.src.utils.errors import WorkflowError
from unittest.mock import MagicMock, patch

# We patch the runner before importing the app to inject our mock
# This is CRITICAL to prevent the app from trying to initialize a real
# WorkflowRunner, which would load configs and require API keys.
mock_runner = MagicMock()

async def mock_streaming_gen():
    yield "Entering node: router_specialist\n"
    yield "Finished node: router_specialist\n"
    yield "FINAL_STATE::{\"status\": \"complete\"}\n"

mock_runner.run.return_value = {"final_output": "success"}
mock_runner.run_streaming.return_value = mock_streaming_gen()

with patch('app.src.api.WorkflowRunner', return_value=mock_runner):
    from app.src.api import app
    from fastapi.testclient import TestClient

@pytest.fixture
def client():
    """Provides a FastAPI TestClient for making requests to the app."""
    with TestClient(app) as c:
        yield c

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test to ensure isolation."""
    mock_runner.reset_mock()
    mock_runner.run.side_effect = None
    mock_runner.run_streaming.side_effect = None

def test_read_root(client):
    """Tests the root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "API is running"}

def test_invoke_graph_sync(client):
    """Tests the synchronous /v1/graph/invoke endpoint."""
    # Arrange
    payload = {"input_prompt": "test prompt"}
    mock_runner.run.return_value = {"final_output": "success"}

    # Act
    response = client.post("/v1/graph/invoke", json=payload)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"final_output": {"final_output": "success"}}
    mock_runner.run.assert_called_with(goal="test prompt")

def test_invoke_graph_sync_handles_runner_error(client):
    """Tests that the sync endpoint returns a 500 if the runner fails."""
    # Arrange
    payload = {"input_prompt": "failing prompt"}
    mock_runner.run.side_effect = WorkflowError("Graph execution failed")

    # Act
    response = client.post("/v1/graph/invoke", json=payload)

    # Assert
    assert response.status_code == 500
    assert "detail" in response.json()
    assert "Workflow execution error: Graph execution failed" in response.json()["detail"]

def test_invoke_graph_sync_invalid_input(client):
    """Tests that the sync endpoint returns a 422 for invalid input."""
    response = client.post("/v1/graph/invoke", json={"wrong_key": "value"})
    assert response.status_code == 422 # Unprocessable Entity

def test_stream_graph_async(client):
    """Tests the asynchronous /v1/graph/stream endpoint."""
    # Arrange
    mock_runner.run_streaming.return_value = mock_streaming_gen()
    payload = {"input_prompt": "test stream prompt"}

    # Act
    response = client.post("/v1/graph/stream", json=payload)

    # Assert
    assert response.status_code == 200
    # The TestClient automatically consumes the stream content
    content = response.text
    assert "Entering node: router_specialist" in content
    assert "FINAL_STATE::{\"status\": \"complete\"}" in content
    mock_runner.run_streaming.assert_called_with(goal="test stream prompt")

def test_stream_graph_async_handles_runner_error(client):
    """Tests that the stream endpoint returns a 500 if the runner fails."""
    # Arrange
    payload = {"input_prompt": "failing stream prompt"}
    mock_runner.run_streaming.side_effect = WorkflowError("Streaming failed")

    # Act
    response = client.post("/v1/graph/stream", json=payload)

    # Assert
    assert response.status_code == 500
    assert "detail" in response.json()
    assert "Workflow streaming error: Streaming failed" in response.json()["detail"]

def test_stream_graph_async_invalid_input(client):
    """Tests that the stream endpoint returns a 422 for invalid input."""
    response = client.post("/v1/graph/stream", json={"wrong_key": "value"})
    assert response.status_code == 422 # Unprocessable Entity