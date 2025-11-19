# app/tests/unit/test_api.py
import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from app.src.utils.errors import WorkflowError

# Per ADR-TS-001, Task 2.3, we patch GraphBuilder to prevent the real graph
# from being built during the FastAPI app's lifespan startup event.
# This is the key to isolating the API tests from the complex workflow logic.
mock_graph_builder_instance = MagicMock()
mock_compiled_app = MagicMock()

# The mock compiled app's methods need to be async where the original is.
mock_compiled_app.astream.return_value = AsyncMock()

mock_graph_builder_instance.build.return_value = mock_compiled_app

# We apply two critical patches:
# 1. GraphBuilder (in the runner module): Prevents the real graph from being built when WorkflowRunner is initialized.
# 2. AdapterFactory (in the graph_builder module): Prevents the real LLM adapters from being created
#    when the GraphBuilder logic is executed. This is the key to stopping live API calls.
with patch('app.src.workflow.runner.GraphBuilder', return_value=mock_graph_builder_instance), \
     patch('app.src.workflow.graph_builder.AdapterFactory', MagicMock()):
    from app.src import api
    from fastapi.testclient import TestClient
 
async def mock_streaming_gen(*args, **kwargs):
    """
    A mock async generator that simulates the output of LangGraph's astream.
    It must yield dictionaries representing the output of each node.
    """
    yield {"router_specialist": {"messages": ["routed to next"]}}
    yield {"file_specialist": {"messages": ["wrote a file"]}}

@pytest.fixture
async def client():
    """
    Provides a FastAPI TestClient. This fixture handles the async lifespan
    of the app to ensure startup events are properly mocked and executed.
    """
    async with api.app.router.lifespan_context(api.app):
        with TestClient(api.app) as c:
            yield c

@pytest.fixture(autouse=True)
async def reset_mocks(client, mocker):  # Depend on client to ensure lifespan has run
    """Reset mocks before each test to ensure isolation."""
    mock_graph_builder_instance.reset_mock()
    mock_compiled_app.reset_mock()

    # Patch the methods on the *instance* of the runner created during app lifespan.
    # This is the correct way to mock instance methods for testing.
    mocker.patch.object(api.workflow_runner, 'run', return_value={"status": "success"})
    mocker.patch.object(api.workflow_runner, 'run_streaming', return_value=mock_streaming_gen())


@pytest.mark.asyncio
async def test_read_root(client: TestClient):
    """Tests the root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "API is running"}

def test_invoke_graph_sync(client):
    """Tests the synchronous /v1/graph/invoke endpoint."""
    # Arrange
    payload = {
        "input_prompt": "test prompt",
        "text_to_process": None,
        "image_to_process": None
    }
    # The mock is already set up in the reset_mocks fixture

    # Act
    response = client.post("/v1/graph/invoke", json=payload)

    # Assert
    assert response.status_code == 200
    assert response.json() == {"final_output": {"status": "success"}}
    api.workflow_runner.run.assert_called_once_with(goal="test prompt", text_to_process=None, image_to_process=None, use_simple_chat=False)

def test_invoke_graph_sync_handles_runner_error(client, mocker):
    """Tests that the sync endpoint returns a 500 if the runner fails."""
    # Arrange
    payload = {"input_prompt": "failing prompt"}
    api.workflow_runner.run.side_effect = WorkflowError("Graph execution failed")

    # Act
    response = client.post("/v1/graph/invoke", json=payload)

    # Assert
    assert response.status_code == 500
    assert "Workflow execution error: Graph execution failed" in response.json()["detail"]

def test_invoke_graph_sync_invalid_input(client):
    """Tests that the sync endpoint returns a 422 for invalid input."""
    response = client.post("/v1/graph/invoke", json={"wrong_key": "value", "text_to_process": None, "image_to_process": None})
    assert response.status_code == 422 # Unprocessable Entity

@pytest.mark.asyncio
async def test_stream_graph_async(client):
    """Tests the asynchronous /v1/graph/stream endpoint."""
    payload = {
        "input_prompt": "test stream prompt",
        "text_to_process": None,
        "image_to_process": None
    }

    # Act
    response = client.post("/v1/graph/stream", json=payload)

    # Assert
    assert response.status_code == 200
    # The TestClient automatically consumes the stream content
    # We check that the formatter correctly processed our mock dicts into status updates
    assert '"status": "Executing specialist: router_specialist..."' in response.text
    assert '"status": "Executing specialist: file_specialist..."' in response.text
    api.workflow_runner.run_streaming.assert_called_once_with(goal="test stream prompt", text_to_process=None, image_to_process=None, use_simple_chat=False)

@pytest.mark.asyncio
async def test_stream_graph_async_handles_runner_error(client, mocker):
    """Tests that the stream endpoint returns a 500 if the runner fails."""
    # Arrange
    payload = {"input_prompt": "failing stream prompt"}
    api.workflow_runner.run_streaming.side_effect = WorkflowError("Streaming failed")

    # Act
    response = client.post("/v1/graph/stream", json=payload)

    # Assert
    assert response.status_code == 500
    assert "Workflow streaming error: Streaming failed" in response.json()["detail"]

@pytest.mark.asyncio
async def test_stream_graph_async_invalid_input(client):
    """Tests that the stream endpoint returns a 422 for invalid input."""
    response = client.post("/v1/graph/stream", json={"wrong_key": "value", "text_to_process": None, "image_to_process": None})
    assert response.status_code == 422 # Unprocessable Entity

@pytest.mark.asyncio
async def test_stream_graph_events_async(client):
    """Tests the standardized /v1/graph/stream/events endpoint."""
    payload = {
        "input_prompt": "test standard stream",
        "text_to_process": None,
        "image_to_process": None
    }

    # Act
    response = client.post("/v1/graph/stream/events", json=payload)

    # Assert
    assert response.status_code == 200
    
    # Parse SSE lines to verify structure robustly
    lines = response.text.strip().split('\n\n')
    found_status = False
    found_router = False
    found_file = False
    
    for line in lines:
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data.get("type") == "status_update":
                found_status = True
            if data.get("source") == "router_specialist":
                found_router = True
            if data.get("source") == "file_specialist":
                found_file = True
                
    assert found_status
    assert found_router
    assert found_file
    
    api.workflow_runner.run_streaming.assert_called_once_with(goal="test standard stream", text_to_process=None, image_to_process=None, use_simple_chat=False)