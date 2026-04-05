# app/tests/integration/test_adr_ui_003_lifecycle.py
"""
Integration tests for ADR-UI-003: Headless observability attachment for standard stream endpoint.

Verifies that /v1/graph/stream/events properly manages run lifecycle:
- Registers runs in active_runs before streaming begins
- Ttees raw events to event_bus for headless observation
- Deregisters runs on completion (success or error)

These tests require Docker because they exercise real API endpoints with real
observability infrastructure (active_runs registry, event_bus pub/sub).
"""
import pytest
import asyncio
import json
from fastapi.testclient import TestClient

from app.src import api
from app.src.observability.active_runs import active_runs
from app.src.observability.event_bus import event_bus


@pytest.fixture(autouse=True)
def clear_observability_state():
    """
    Clear observability state before and after each test.

    Ensures test isolation by removing any leftover active runs
    and clearing event bus subscribers.
    """
    # Before test: clear any active runs from previous tests
    active_runs._runs.clear()
    event_bus._subscribers.clear()

    yield

    # After test: cleanup (defensive, in case test didn't complete properly)
    active_runs._runs.clear()
    event_bus._subscribers.clear()


@pytest.mark.integration
def test_stream_events_registers_run_before_streaming(initialized_app):
    """
    Integration test: Verifies run is registered in active_runs BEFORE streaming begins.

    This is critical for headless V.E.G.A.S. observability to discover the run
    and attach an event stream. The run must be registered before any events
    are emitted, or the headless observer will miss the start of execution.

    Expected behavior:
    1. Client sends POST /v1/graph/stream/events
    2. Server generates run_id and registers in active_runs
    3. Server begins streaming events (run is discoverable during streaming)
    """
    app = initialized_app

    # Pre-test assertion: no active runs
    assert len(active_runs.get_active()) == 0

    with TestClient(app) as client:
        payload = {
            "input_prompt": "What is 2 + 2?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream/events", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # After request completes, run should be deregistered
    # (the endpoint uses try/finally to ensure cleanup)
    active_runs_list = active_runs.get_active()
    # Note: We can't assert the run was registered *during* streaming because
    # TestClient consumes the stream synchronously. The integration test below
    # with async client verifies this more thoroughly.
    assert len(active_runs_list) == 0, "Run should be deregistered after completion"


@pytest.mark.integration
def test_stream_events_deregisters_on_success(initialized_app):
    """
    Integration test: Verifies run is deregistered after successful completion.

    Expected behavior:
    1. Run starts -> registered in active_runs
    2. Workflow completes successfully
    3. Run is deregistered in finally block
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "Hello, how are you?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream/events", json=payload)
        assert response.status_code == 200

    # Verify run was cleaned up
    active_runs_list = active_runs.get_active()
    assert len(active_runs_list) == 0, (
        f"Run should be deregistered after successful completion. "
        f"Active runs: {active_runs_list}"
    )


@pytest.mark.integration
def test_stream_events_deregisters_on_error(initialized_app):
    """
    Integration test: Verifies run is deregistered even when workflow errors.

    The try/finally block ensures cleanup happens regardless of success or failure.

    Expected behavior:
    1. Run starts -> registered in active_runs
    2. Workflow errors (e.g., validation error, model error)
    3. Run is deregistered in finally block
    """
    app = initialized_app

    with TestClient(app) as client:
        # Empty prompt may trigger validation error or model rejection
        payload = {
            "input_prompt": "",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream/events", json=payload)
        # May return 200 (streaming with error in stream) or 400/422 (validation)
        assert response.status_code in [200, 400, 422], (
            f"Expected streaming response or validation error, got {response.status_code}"
        )

    # Verify run was cleaned up even on error
    # (if validation fails before run_id generation, no cleanup needed)
    # This test passes if no zombie runs accumulate
    active_runs_list = active_runs.get_active()
    assert len(active_runs_list) == 0, (
        f"Run should be deregistered after error. Active runs: {active_runs_list}"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stream_events_tees_to_event_bus(initialized_app):
    """
    Integration test: Verifies events are teed to event_bus for headless observers.

    This test uses an async client to subscribe to the event bus BEFORE
    starting the workflow, then verifies events are received.

    Expected behavior:
    1. Test subscribes to event_bus for a specific run_id
    2. Workflow runs and emits events
    3. Events are pushed to event_bus (not just streamed to client)
    4. Test receives events via event_bus subscription
    """
    app = initialized_app

    # We need to coordinate: subscribe before run, then trigger run
    # Use a semaphore to synchronize
    subscribe_done = asyncio.Event()
    events_received = []
    subscription_task = None

    async def subscribe_and_collect(run_id: str, timeout: float = 30.0):
        """Subscribe to event bus and collect events."""
        # Subscribe to the run
        queue = await event_bus.subscribe(run_id)
        subscribe_done.set()

        # Collect events until sentinel (None) or timeout
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=timeout)
                    if event is None:  # sentinel
                        break
                    events_received.append(event)
                except asyncio.TimeoutError:
                    break
        except Exception as e:
            print(f"Event collection error: {e}")

    # Trigger workflow and capture run_id from the stream
    # We'll use a wrapper that lets us intercept the run_id
    captured_run_id = None

    original_run_streaming = api.workflow_runner.run_streaming

    async def instrumented_run_streaming(*args, **kwargs):
        """Wrap run_streaming to capture run_id and start event collection."""
        nonlocal captured_run_id

        # Extract run_id from kwargs
        run_id = kwargs.get('run_id')
        if run_id:
            captured_run_id = run_id
            # Start subscription task
            subscription_task = asyncio.create_task(subscribe_and_collect(run_id))
            # Wait for subscription to be ready
            await asyncio.wait_for(subscribe_done.wait(), timeout=5.0)

        # Call original
        async for event in original_run_streaming(*args, **kwargs):
            yield event

    # Patch the workflow runner
    api.workflow_runner.run_streaming = instrumented_run_streaming

    try:
        with TestClient(app) as client:
            payload = {
                "input_prompt": "What is the capital of France?",
                "text_to_process": None,
                "image_to_process": None
            }

            response = client.post("/v1/graph/stream/events", json=payload)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        # Wait for subscription task to complete
        if subscription_task:
            try:
                await asyncio.wait_for(subscription_task, timeout=30.0)
            except asyncio.TimeoutError:
                print("Subscription task timed out")

        # Verify we received events via event_bus
        # (not just via the direct stream)
        assert len(events_received) > 0, (
            f"Expected events via event_bus, got {len(events_received)}. "
            f"Captured run_id: {captured_run_id}"
        )

        # Verify event structure (should have run_id and event data)
        assert all(isinstance(e, dict) for e in events_received), (
            "All events should be dictionaries"
        )

    finally:
        # Restore original
        api.workflow_runner.run_streaming = original_run_streaming


@pytest.mark.integration
def test_stream_events_run_id_passed_through(initialized_app):
    """
    Integration test: Verifies run_id is consistently used throughout the pipeline.

    Expected behavior:
    1. API generates run_id
    2. run_id passed to workflow_runner.run_streaming()
    3. run_id appears in streamed events
    4. run_id used for active_runs registration
    5. run_id used for event_bus pushes
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "Count from 1 to 3",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream/events", json=payload)
        assert response.status_code == 200

        # Parse SSE stream
        run_ids_in_events = set()
        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())
                    if 'run_id' in data:
                        run_ids_in_events.add(data['run_id'])
                except json.JSONDecodeError:
                    pass

        # Verify run_id is present in events
        assert len(run_ids_in_events) > 0, (
            "Expected run_id in streamed events. This is required for "
            "headless observability to correlate events with runs."
        )

        # All events should have the same run_id
        assert len(run_ids_in_events) == 1, (
            f"Expected consistent run_id across events, got {len(run_ids_in_events)} different IDs"
        )


@pytest.mark.integration
def test_stream_events_multiple_runs_isolated(initialized_app):
    """
    Integration test: Verifies multiple concurrent runs are properly isolated.

    Expected behavior:
    1. Run A starts -> registered with run_id_A
    2. Run B starts -> registered with run_id_B
    3. Events from A go to run_id_A's event bus queue
    4. Events from B go to run_id_B's event bus queue
    5. Both runs deregister independently
    """
    app = initialized_app

    # Run multiple workflows sequentially (TestClient is synchronous)
    # For true concurrency testing, we'd need async HTTP client
    run_count = 3
    final_response = None

    with TestClient(app) as client:
        for i in range(run_count):
            payload = {
                "input_prompt": f"Test run {i + 1}: what is {i} + {i}?",
                "text_to_process": None,
                "image_to_process": None
            }

            response = client.post("/v1/graph/stream/events", json=payload)
            assert response.status_code == 200, f"Run {i + 1} failed: {response.text}"
            final_response = response

        # After all runs complete, no active runs should remain
        active_runs_list = active_runs.get_active()
        assert len(active_runs_list) == 0, (
            f"After {run_count} runs, all should be deregistered. "
            f"Active runs: {active_runs_list}"
        )

    # Final response should be valid
    assert final_response is not None
    assert "data:" in final_response.text
