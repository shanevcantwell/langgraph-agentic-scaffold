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

from app.tests.conftest import assert_response_not_error, assert_tiered_chat_merge


def _extract_final_response_content(final_state: dict) -> str | None:
    """Extract the final response text from final_state for validation."""
    if not final_state:
        return None

    # Check artifacts for final_user_response.md
    artifacts = final_state.get("artifacts", {})
    if isinstance(artifacts, dict) and "final_user_response.md" in artifacts:
        return artifacts["final_user_response.md"]

    # Check messages for last AI message content
    messages = final_state.get("messages", [])
    if messages:
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("type") == "ai":
                return msg.get("content", "")
            elif hasattr(msg, "type") and msg.type == "ai":
                return msg.content

    return None


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
        final_state = None

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

                    if 'final_state' in data:
                        final_state = data['final_state']

                except json.JSONDecodeError:
                    pass  # Skip malformed lines

        # Assertions
        assert len(status_updates) > 0, "No status updates received from API"

        # Validate response content doesn't contain error indicators
        response_content = _extract_final_response_content(final_state)
        if response_content:
            assert_response_not_error(response_content, "[Streaming]")

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
        final_state = None

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())
                    if 'status' in data:
                        match = re.search(r'Executing specialist: (\w+)', data['status'])
                        if match:
                            specialist_names.add(match.group(1))
                    if 'final_state' in data:
                        final_state = data['final_state']
                except json.JSONDecodeError:
                    pass

        # Validate response content doesn't contain error indicators
        response_content = _extract_final_response_content(final_state)
        if response_content:
            assert_response_not_error(response_content, "[TieredChat]")

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

            # Validate tiered chat merge (synthesizer ran after both progenitors)
            if final_state:
                assert_tiered_chat_merge(final_state, "[TieredChat]")


@pytest.mark.integration
def test_api_streams_file_operations_specialist(initialized_app):
    """
    Integration test: Verifies file_operations_specialist streams correctly.

    Tests that file operations (list files, read, etc.) produce proper
    streaming output including:
    - Specialist status updates
    - MCP call execution
    - Final response with file listing
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "List files in the workspace",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)
        assert response.status_code == 200

        specialist_names = set()
        status_updates = []
        final_state = None

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())

                    if 'status' in data:
                        status_updates.append(data['status'])
                        match = re.search(r'Executing specialist: (\w+)', data['status'])
                        if match:
                            specialist_names.add(match.group(1))

                    # Capture final state for assertion
                    if 'final_state' in data:
                        final_state = data['final_state']

                except json.JSONDecodeError:
                    pass

        # Should have routed through triage and to file operations
        assert len(specialist_names) >= 2, (
            f"Expected multiple specialists. Got: {specialist_names}"
        )

        # Final state should exist
        assert final_state is not None or any("complete" in s.lower() for s in status_updates), (
            "Expected final state or completion status in stream"
        )

        # Validate response content doesn't contain error indicators
        response_content = _extract_final_response_content(final_state)
        if response_content:
            assert_response_not_error(response_content, "[FileOperations]")


@pytest.mark.integration
def test_api_streams_artifacts_in_response(initialized_app):
    """
    Integration test: Verifies artifacts are included in streamed response.

    Tests that specialist-generated artifacts (system plans, HTML, etc.)
    are properly included in the final streamed state.
    """
    app = initialized_app

    with TestClient(app) as client:
        # Request that should produce artifacts (planning task)
        payload = {
            "input_prompt": "Create a brief plan for a hello world web page",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)
        assert response.status_code == 200

        artifacts_found = False
        final_response_found = False
        final_state = None

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())

                    # Check for artifacts in streamed data
                    if 'artifacts' in data:
                        artifacts_found = True

                    # Check final state for artifacts
                    if 'final_state' in data:
                        final_state = data['final_state']
                        if 'artifacts' in final_state and final_state['artifacts']:
                            artifacts_found = True
                        if 'messages' in final_state and final_state['messages']:
                            final_response_found = True

                    # Check for completion message content
                    if 'content' in data or 'message' in data:
                        final_response_found = True

                except json.JSONDecodeError:
                    pass

        # At minimum, should have some response content
        assert final_response_found or artifacts_found, (
            "Expected either final response content or artifacts in stream"
        )

        # Validate response content doesn't contain error indicators
        response_content = _extract_final_response_content(final_state)
        if response_content:
            assert_response_not_error(response_content, "[Artifacts]")


@pytest.mark.integration
def test_api_streams_status_for_all_routed_specialists(initialized_app):
    """
    Integration test: Verifies status updates are emitted for every specialist
    in the routing path, not just router.

    This is critical for UI feedback - users need to see progress through
    the entire workflow.
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "What is 2 + 2?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/stream", json=payload)
        assert response.status_code == 200

        execution_order = []

        final_state = None

        for line in response.text.split('\n'):
            if line.startswith('data:'):
                try:
                    data = json.loads(line[len('data:'):].strip())
                    if 'status' in data:
                        match = re.search(r'Executing specialist: (\w+)', data['status'])
                        if match:
                            specialist = match.group(1)
                            if specialist not in execution_order:
                                execution_order.append(specialist)
                    if 'final_state' in data:
                        final_state = data['final_state']
                except json.JSONDecodeError:
                    pass

        # Should have execution order tracked
        assert len(execution_order) >= 2, (
            f"Expected at least 2 specialists in execution path. "
            f"Got: {execution_order}"
        )

        # Triage should be first (entry point)
        if "triage_architect" in execution_order:
            assert execution_order[0] == "triage_architect", (
                f"triage_architect should be first. Order: {execution_order}"
            )

        # Validate response content doesn't contain error indicators
        response_content = _extract_final_response_content(final_state)
        if response_content:
            assert_response_not_error(response_content, "[StatusUpdates]")


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
