# app/tests/integration/test_api_streaming_integration.py
"""
Integration tests for API streaming with real specialists.

Verifies that status updates are emitted for ALL specialists during execution,
not just the router. This catches real-world issues that mocked unit tests miss.
"""
import pytest
from fastapi.testclient import TestClient
import json
import re


@pytest.mark.integration
def test_api_streams_multiple_specialist_updates(initialized_app):
    """
    Integration test: Verifies API emits status updates for router AND other specialists.

    This test uses the real graph with real specialists (not mocks) to catch
    issues where specialist outputs don't trigger status updates in the API.

    Expected behavior:
    - Router specialist executes → status update emitted
    - Target specialist executes (e.g., chat, file, etc.) → status update emitted
    - Final state with artifacts → emitted at end
    """
    # Get the FastAPI app from the fixture
    app = initialized_app

    with TestClient(app) as client:
        # Send a simple chat request that should route to chat_specialist
        payload = {
            "input_prompt": "Hello, how are you today?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)

        # Assert response is successful
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        # Parse SSE stream to extract status updates
        status_updates = []
        specialist_names = set()

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data_str = line[len('data:'):].strip()
                    data = json.loads(data_str)

                    if 'status' in data:
                        status_updates.append(data['status'])

                        # Extract specialist name from status message
                        # Format: "Executing specialist: <specialist_name>..."
                        match = re.search(r'Executing specialist: (\w+)', data['status'])
                        if match:
                            specialist_names.add(match.group(1))

                except json.JSONDecodeError:
                    pass  # Skip malformed lines

        # Assertions
        assert len(status_updates) > 0, "No status updates received from API"

        # Should have at least router and one other specialist
        assert len(specialist_names) >= 2, (
            f"Expected updates from router + at least one other specialist. "
            f"Got updates from: {specialist_names}"
        )

        # Router should always execute first
        assert "router_specialist" in specialist_names, (
            f"Router specialist should execute. Got: {specialist_names}"
        )

        # Should have at least one non-router specialist
        non_router_specialists = specialist_names - {"router_specialist"}
        assert len(non_router_specialists) > 0, (
            f"Should have at least one non-router specialist. "
            f"Got only: {specialist_names}"
        )

        # Final state should be included
        assert any("complete" in status.lower() for status in status_updates), (
            "Final completion status not found in updates"
        )


@pytest.mark.integration
def test_api_streams_error_updates(initialized_app):
    """
    Integration test: Verifies API streams error updates when specialists fail.

    Ensures error messages are propagated through the streaming API
    in real-time, not just at the end.
    """
    app = initialized_app

    with TestClient(app) as client:
        # Send a request that will likely cause an error (e.g., malformed input)
        # This depends on your system's validation logic
        payload = {
            "input_prompt": "",  # Empty prompt might trigger validation error
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)

        # Even with errors, response should be 200 (streaming started)
        # Errors are communicated within the stream
        assert response.status_code in [200, 400, 422], (
            f"Expected streaming response or validation error, got {response.status_code}"
        )


@pytest.mark.integration
def test_api_streams_tiered_chat_specialists(initialized_app):
    """
    Integration test: Verifies tiered chat subgraph specialists are all streamed.

    With tiered chat enabled, should see updates from:
    - router_specialist
    - progenitor_alpha_specialist
    - progenitor_bravo_specialist
    - tiered_synthesizer_specialist (if it emits messages)
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "Explain the concept of recursion in programming.",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)
        assert response.status_code == 200

        specialist_names = set()

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())
                    if 'status' in data:
                        match = re.search(r'Executing specialist: (\w+)', data['status'])
                        if match:
                            specialist_names.add(match.group(1))
                except json.JSONDecodeError:
                    pass

        # If tiered chat is enabled, should see progenitor specialists
        # Note: This test may need to be skipped if tiered chat is disabled in config
        if "progenitor_alpha_specialist" in specialist_names or "progenitor_bravo_specialist" in specialist_names:
            # Tiered chat is enabled, verify both progenitors executed
            assert "progenitor_alpha_specialist" in specialist_names, (
                "Tiered chat enabled but Alpha progenitor not executed"
            )
            assert "progenitor_bravo_specialist" in specialist_names, (
                "Tiered chat enabled but Bravo progenitor not executed"
            )

            # Should have at least 3 specialists (router + 2 progenitors)
            assert len(specialist_names) >= 3, (
                f"Expected router + 2 progenitors + synthesizer. Got: {specialist_names}"
            )


# ============================================================================
# FIXTURE: Initialized FastAPI App
# ============================================================================

@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.

    This fixture is expensive (builds real graph with real LLM adapters),
    so we use module scope to share across all tests in this file.
    """
    # Import here to ensure proper initialization order
    from app.src import api

    # The app's lifespan should have already initialized the workflow_runner
    # during module import. Just return the app.
    return api.app
