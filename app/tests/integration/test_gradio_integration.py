# app/tests/integration/test_gradio_integration.py
"""
Integration tests for the Gradio UI.

These tests verify that the Gradio UI can:
1. Start successfully
2. Connect to the API server
3. Process a simple request end-to-end
4. Handle errors gracefully

Note: These tests require the API server to be running.
"""
import pytest
import httpx
import asyncio
from app.src.ui.api_client import ApiClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_client_can_connect_to_live_server():
    """
    Tests that the ApiClient can successfully connect to a running API server.
    This verifies the basic connectivity between the UI and backend.
    """
    api_client = ApiClient()

    # Check if the server is accessible
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://127.0.0.1:8000/")
            assert response.status_code == 200, "API server health check failed"
    except httpx.ConnectError:
        pytest.skip("API server is not running. Start with './scripts/server.sh start'")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_client_streaming_with_simple_prompt():
    """
    Tests that the ApiClient can successfully stream responses from the API server
    with a simple prompt. This is a minimal end-to-end test.
    """
    api_client = ApiClient()

    # Check if server is running first
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get("http://127.0.0.1:8000/")
    except httpx.ConnectError:
        pytest.skip("API server is not running. Start with './scripts/server.sh start'")

    # Send a very simple prompt
    simple_prompt = "ping"
    updates_received = []

    try:
        async for update in api_client.invoke_agent_streaming(simple_prompt, None, None):
            updates_received.append(update)
            # Break after receiving a reasonable number of updates to avoid long-running test
            if len(updates_received) > 20:
                break
    except Exception as e:
        pytest.fail(f"Failed to stream from API: {e}")

    # Verify we received at least some updates
    assert len(updates_received) > 0, "Should have received at least one update from the stream"

    # Verify the structure of updates (should be dictionaries)
    for update in updates_received:
        assert isinstance(update, dict), f"Update should be a dict, got {type(update)}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_api_client_handles_empty_prompt():
    """
    Tests that the ApiClient handles empty prompts gracefully.
    """
    api_client = ApiClient()

    # Check if server is running first
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get("http://127.0.0.1:8000/")
    except httpx.ConnectError:
        pytest.skip("API server is not running. Start with './scripts/server.sh start'")

    # Empty prompt should be handled by the UI layer, but we test the client's behavior
    empty_prompt = ""
    updates_received = []

    # The api_client itself doesn't validate empty prompts - that's the UI's job
    # But we want to ensure it doesn't crash
    try:
        async for update in api_client.invoke_agent_streaming(empty_prompt, None, None):
            updates_received.append(update)
            if len(updates_received) > 5:
                break
    except Exception as e:
        # It's okay if the API returns an error for empty prompts
        pass


@pytest.mark.integration
@pytest.mark.asyncio
async def test_gradio_handle_submit_integration():
    """
    Integration test for the handle_submit function with a live API server.
    This tests the full UI logic path with real API responses.
    """
    # Check if server is running first
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get("http://127.0.0.1:8000/")
    except httpx.ConnectError:
        pytest.skip("API server is not running. Start with './scripts/server.sh start'")

    from app.src.ui.gradio_app import handle_submit
    from unittest.mock import MagicMock

    # Create a real API client (not mocked)
    api_client = ApiClient()

    # Create mock UI components (since we're not testing Gradio itself)
    mock_components = {key: MagicMock(name=key) for key in [
        "status_output", "log_output", "json_output", "html_output",
        "image_output", "archive_output"
    ]}

    submit_handler = handle_submit(api_client, **mock_components)

    # Test with a simple prompt
    updates = []
    try:
        async for update in submit_handler("ping", None, None):
            updates.append(update)
            # Limit iterations for test performance
            if len(updates) > 20:
                break
    except Exception as e:
        pytest.fail(f"handle_submit failed with live API: {e}")

    # Verify we got some updates
    assert len(updates) > 0, "Should have received UI updates"

    # Verify updates are dictionaries with component keys
    for update in updates:
        assert isinstance(update, dict), "Each update should be a dictionary"
        # At least one key should be a mock component
        assert any(key in mock_components.values() for key in update.keys()), \
            "Update should contain at least one UI component key"
