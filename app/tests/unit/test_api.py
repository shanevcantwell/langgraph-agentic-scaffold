# app/tests/unit/test_api.py
import pytest
import json
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from app.src.utils.errors import WorkflowError
from fastapi.testclient import TestClient

# Per ADR-TS-001, Task 2.3, we patch GraphBuilder to prevent the real graph
# from being built during the FastAPI app's lifespan startup event.
# This is the key to isolating the API tests from the complex workflow logic.
mock_graph_builder_instance = MagicMock()
mock_graph_builder_instance.return_value = mock_graph_builder_instance  # When called as class, return self
mock_compiled_app = MagicMock()

# The mock compiled app's methods need to be async where the original is.
mock_compiled_app.astream.return_value = AsyncMock()

mock_graph_builder_instance.build.return_value = mock_compiled_app

# Mock external MCP lifecycle to prevent Docker connection attempts (fixes hang issue)
mock_graph_builder_instance.initialize_external_mcp = AsyncMock()
mock_graph_builder_instance.cleanup_external_mcp = AsyncMock()


@pytest.fixture(scope="module")
def patched_api():
    """
    Provides the api module with GraphBuilder and AdapterFactory mocked.

    This fixture properly isolates the mocking to this test module by:
    1. Starting patches before importing api
    2. Clearing sys.modules cache for api so it imports fresh with patches
    3. Stopping patches and clearing cache again after tests complete

    This prevents the test isolation bug where api.workflow_runner would
    remain a MagicMock for subsequent integration tests.
    """
    # Create and start patches
    graph_builder_patch = patch('app.src.workflow.runner.GraphBuilder', mock_graph_builder_instance)
    adapter_factory_patch = patch('app.src.workflow.graph_builder.AdapterFactory', MagicMock())

    graph_builder_patch.start()
    adapter_factory_patch.start()

    # Clear any existing api imports so we get a fresh import with patches active
    mods_to_remove = [k for k in list(sys.modules.keys()) if 'app.src.api' in k]
    for mod in mods_to_remove:
        del sys.modules[mod]

    # Import api fresh with patches active
    from app.src import api

    yield api

    # Cleanup: stop patches
    graph_builder_patch.stop()
    adapter_factory_patch.stop()

    # Remove api from sys.modules so integration tests get the real version
    mods_to_remove = [k for k in list(sys.modules.keys()) if 'app.src.api' in k]
    for mod in mods_to_remove:
        del sys.modules[mod]
 
async def mock_streaming_gen(*args, **kwargs):
    """
    A mock async generator that simulates the output of LangGraph's astream.
    It must yield dictionaries representing the output of each node.
    """
    yield {"router_specialist": {"messages": ["routed to next"]}}
    yield {"file_specialist": {"messages": ["wrote a file"]}}


@pytest.fixture
async def client(patched_api):
    """
    Provides a FastAPI TestClient. This fixture handles the async lifespan
    of the app to ensure startup events are properly mocked and executed.
    """
    async with patched_api.app.router.lifespan_context(patched_api.app):
        with TestClient(patched_api.app) as c:
            yield c


@pytest.fixture
def mock_active_runs(mocker):
    """
    Mock active_runs registry for ADR-UI-003 lifecycle testing.

    Returns a MagicMock that tracks register/deregister calls.
    """
    mock_registry = mocker.MagicMock()
    mocker.patch('app.src.api.active_runs', mock_registry)
    return mock_registry


@pytest.fixture
def mock_event_bus(mocker):
    """
    Mock event_bus for ADR-UI-003 lifecycle testing.

    Returns a MagicMock that tracks push/close calls.
    """
    mock_bus = mocker.MagicMock()
    mock_bus.push = mocker.AsyncMock()
    mock_bus.close = mocker.AsyncMock()
    mocker.patch('app.src.api.event_bus', mock_bus)
    return mock_bus


@pytest.fixture(autouse=True)
async def reset_mocks(client, patched_api, mocker):  # Depend on client to ensure lifespan has run
    """Reset mocks before each test to ensure isolation."""
    mock_graph_builder_instance.reset_mock()
    mock_compiled_app.reset_mock()

    # Patch the methods on the *instance* of the runner created during app lifespan.
    # This is the correct way to mock instance methods for testing.
    mocker.patch.object(patched_api.workflow_runner, 'run', return_value={"status": "success"})
    mocker.patch.object(patched_api.workflow_runner, 'run_streaming', return_value=mock_streaming_gen())


@pytest.mark.asyncio
async def test_read_root(client: TestClient):
    """Tests the root health check endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "API is running"}

def test_invoke_graph_sync(client, patched_api):
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
    patched_api.workflow_runner.run.assert_called_once()
    call_kwargs = patched_api.workflow_runner.run.call_args.kwargs
    assert call_kwargs["goal"] == "test prompt"
    assert call_kwargs["text_to_process"] is None
    assert call_kwargs["use_simple_chat"] is False
    assert call_kwargs["subagent"] is False
    assert call_kwargs["run_id"] is not None  # #203: UUID generated by invoke_graph()

def test_invoke_graph_sync_handles_runner_error(client, patched_api, mocker):
    """Tests that the sync endpoint returns a 500 if the runner fails."""
    # Arrange
    payload = {"input_prompt": "failing prompt"}
    patched_api.workflow_runner.run.side_effect = WorkflowError("Graph execution failed")

    # Act
    response = client.post("/v1/graph/invoke", json=payload)

    # Assert
    assert response.status_code == 500
    assert "Workflow execution error: Graph execution failed" in response.json()["detail"]

def test_invoke_graph_sync_invalid_input(client):
    """Tests that the sync endpoint returns a 422 for invalid input."""
    response = client.post("/v1/graph/invoke", json={"wrong_key": "value", "text_to_process": None, "image_to_process": None})
    assert response.status_code == 422 # Unprocessable Entity

# Tests for POST /v1/graph/stream removed — endpoint removed in ADR-UI-003 WS3.
# OpenAI-compatible endpoint tests are in test_openai_*.py.

@pytest.mark.asyncio
async def test_stream_graph_events_async(client, patched_api):
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

    # Verify run_streaming was called with correct arguments including run_id (ADR-UI-003)
    call_args = patched_api.workflow_runner.run_streaming.call_args
    assert call_args.kwargs["goal"] == "test standard stream"
    assert call_args.kwargs["text_to_process"] is None
    assert call_args.kwargs["image_to_process"] is None
    assert call_args.kwargs["use_simple_chat"] is False
    assert call_args.kwargs["conversation_id"] is None
    assert call_args.kwargs["prior_messages"] is None
    # run_id should be a non-empty string (UUID generated for lifecycle tracking)
    assert "run_id" in call_args.kwargs
    assert isinstance(call_args.kwargs["run_id"], str)
    assert len(call_args.kwargs["run_id"]) > 0


# ============================================================================
# ADR-UI-003: Headless Observability Lifecycle Tests
# ============================================================================

@pytest.mark.asyncio
async def test_stream_events_registers_run_before_streaming(
    client, patched_api, mock_active_runs, mocker
):
    """
    ADR-UI-003: Verify run is registered in active_runs before streaming begins.

    The run must be registered before any events are emitted so headless
    V.E.G.A.S. observability can discover and attach to the run.
    """
    payload = {
        "input_prompt": "test registration",
        "text_to_process": None,
        "image_to_process": None
    }

    response = client.post("/v1/graph/stream/events", json=payload)
    assert response.status_code == 200

    # Verify register was called with run_id and info dict
    assert mock_active_runs.register.called
    call_args = mock_active_runs.register.call_args
    assert isinstance(call_args.args[0], str)  # run_id
    assert isinstance(call_args.args[1], dict)  # info dict
    assert call_args.args[1].get("model") == "standard-stream"
    assert call_args.args[1].get("status") == "streaming"


@pytest.mark.asyncio
async def test_stream_events_deregisters_run_on_success(
    client, patched_api, mock_active_runs, mock_event_bus, mocker
):
    """
    ADR-UI-003: Verify run is deregistered after successful completion.

    The finally block ensures cleanup happens on successful completion.
    """
    payload = {
        "input_prompt": "test deregister on success",
        "text_to_process": None,
        "image_to_process": None
    }

    response = client.post("/v1/graph/stream/events", json=payload)
    assert response.status_code == 200

    # Verify deregister was called (in finally block)
    assert mock_active_runs.deregister.called
    call_args = mock_active_runs.deregister.call_args
    assert isinstance(call_args.args[0], str)  # run_id


@pytest.mark.asyncio
async def test_stream_events_deregisters_run_on_error(
    client, patched_api, mock_active_runs, mocker
):
    """
    ADR-UI-003: Verify run is deregistered even when workflow errors.

    The try/finally block ensures cleanup happens regardless of success or failure.
    """
    # Make run_streaming raise an error
    mocker.patch.object(
        patched_api.workflow_runner,
        'run_streaming',
        side_effect=WorkflowError("Simulated workflow error")
    )

    payload = {
        "input_prompt": "test deregister on error",
        "text_to_process": None,
        "image_to_process": None
    }

    response = client.post("/v1/graph/stream/events", json=payload)
    # Should return 500 for WorkflowError
    assert response.status_code == 500

    # Verify register was still called
    assert mock_active_runs.register.called

    # Verify deregister was called in finally block despite error
    assert mock_active_runs.deregister.called


@pytest.mark.asyncio
async def test_stream_events_pushes_to_event_bus(
    client, patched_api, mock_event_bus, mocker
):
    """
    ADR-UI-003: Verify events are teed to event_bus for headless observers.

    Each event from the raw stream should be pushed to the event_bus.
    """
    # Create a mock stream that yields events with run_id
    async def mock_stream_with_run_id():
        test_run_id = "test-run-123"
        yield {"run_id": test_run_id, "type": "test_event", "data": "event1"}
        yield {"run_id": test_run_id, "type": "test_event", "data": "event2"}

    mocker.patch.object(
        patched_api.workflow_runner,
        'run_streaming',
        return_value=mock_stream_with_run_id()
    )

    payload = {
        "input_prompt": "test event bus push",
        "text_to_process": None,
        "image_to_process": None
    }

    response = client.post("/v1/graph/stream/events", json=payload)
    assert response.status_code == 200

    # Verify push was called for each event
    assert mock_event_bus.push.call_count >= 2
    # First call should have run_id and event
    first_call = mock_event_bus.push.call_args_list[0]
    assert isinstance(first_call.args[0], str)  # run_id
    assert isinstance(first_call.args[1], dict)  # event


@pytest.mark.asyncio
async def test_stream_events_closes_event_bus_on_completion(
    client, patched_api, mock_event_bus, mocker
):
    """
    ADR-UI-003: Verify event_bus.close() is called at end of stream.

    The close() call sends a sentinel (None) to signal end-of-stream to
    headless observers.
    """
    async def mock_stream():
        yield {"run_id": "test-run", "type": "event"}

    mocker.patch.object(
        patched_api.workflow_runner,
        'run_streaming',
        return_value=mock_stream()
    )

    payload = {
        "input_prompt": "test event bus close",
        "text_to_process": None,
        "image_to_process": None
    }

    response = client.post("/v1/graph/stream/events", json=payload)
    assert response.status_code == 200

    # Verify close was called with run_id
    assert mock_event_bus.close.called
    call_args = mock_event_bus.close.call_args
    assert isinstance(call_args.args[0], str)  # run_id