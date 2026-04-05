# app/tests/unit/test_api_client.py
#
# Tests for the Gradio UI API client (ADR-UI-003 WS3: OpenAI-compatible endpoint).
#
import pytest
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import base64
import json
import httpx
from PIL import Image
import io

from app.src.ui.api_client import ApiClient

@pytest.fixture
def api_client():
    """Provides an instance of the ApiClient."""
    return ApiClient()

@pytest.fixture
def mock_httpx_client():
    """
    Mocks the httpx.AsyncClient to prevent actual HTTP calls.
    """
    mock_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)

    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client_instance

    mock_response_cm = AsyncMock()
    mock_response_cm.__aenter__.return_value = mock_response
    mock_client_instance.stream.return_value = mock_response_cm

    with patch("app.src.ui.api_client.httpx.AsyncClient", return_value=mock_client_cm):
        yield mock_client_instance, mock_response


def test_encode_image_to_base64(api_client):
    """Tests the internal image encoding utility."""
    mock_image_data = b"fake_image_bytes"
    expected_base64 = base64.b64encode(mock_image_data).decode('utf-8')

    with patch("builtins.open", mock_open(read_data=mock_image_data)) as mock_file:
        result = api_client._encode_image_to_base64("fake_path.jpg")

        mock_file.assert_called_once_with("fake_path.jpg", "rb")
        assert result == expected_base64


@pytest.mark.asyncio
async def test_invoke_agent_streaming_success(api_client, mock_httpx_client):
    """Tests the happy path: OpenAI SSE chunks → accumulated content → final yield."""
    mock_client, mock_response = mock_httpx_client

    async def stream_generator():
        yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"Hello "}}]}'
        yield 'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"world"}}]}'
        yield 'data: [DONE]'

    mock_response.aiter_lines.return_value = stream_generator()

    updates = [update async for update in api_client.invoke_agent_streaming("test prompt", None, None)]

    # Two "Receiving response..." status updates + one final state with accumulated content
    assert any("Workflow complete." in u.get("status", "") for u in updates), \
        f"Expected workflow complete status. Got: {updates}"
    final = [u for u in updates if "archive" in u]
    assert len(final) == 1
    assert final[0]["archive"] == "Hello world"

    # Verify the mock was called with OpenAI format
    mock_client.stream.assert_called_once()
    call_kwargs = mock_client.stream.call_args
    assert call_kwargs[0][0] == "POST"
    assert "/v1/chat/completions" in call_kwargs[0][1]
    sent_payload = call_kwargs[1]['json']
    assert sent_payload["model"] == "las-default"
    assert sent_payload["stream"] is True
    assert sent_payload["messages"][0]["role"] == "user"
    assert sent_payload["messages"][0]["content"] == "test prompt"


@pytest.mark.asyncio
async def test_invoke_agent_streaming_simple_chat_mode(api_client, mock_httpx_client):
    """Tests that use_simple_chat=True sends model=las-simple."""
    mock_client, mock_response = mock_httpx_client

    async def stream_generator():
        yield 'data: [DONE]'

    mock_response.aiter_lines.return_value = stream_generator()

    _ = [update async for update in api_client.invoke_agent_streaming("test", None, None, use_simple_chat=True)]

    sent_payload = mock_client.stream.call_args[1]['json']
    assert sent_payload["model"] == "las-simple"


@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_file(api_client, mock_httpx_client):
    """Tests that text files are injected as system messages."""
    mock_client, mock_response = mock_httpx_client

    async def empty_gen():
        yield 'data: [DONE]'

    mock_response.aiter_lines.return_value = empty_gen()

    mock_text_file = MagicMock()
    mock_text_file.name = "test.txt"

    with patch("builtins.open", mock_open(read_data="file content")):
        _ = [update async for update in api_client.invoke_agent_streaming("prompt", mock_text_file, None)]

    sent_payload = mock_client.stream.call_args[1]['json']
    messages = sent_payload["messages"]
    # System message with file content should be first
    assert messages[0]["role"] == "system"
    assert "file content" in messages[0]["content"]
    # User message should be second
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "prompt"


@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_malformed_json(api_client, mock_httpx_client):
    """Tests robust error handling when SSE data is invalid JSON."""
    mock_client, mock_response = mock_httpx_client

    async def gen():
        yield "data: {'invalid-json':,}"
        yield "data: [DONE]"

    mock_response.aiter_lines.return_value = gen()

    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    error_updates = [u for u in updates if "logs" in u and "[UI-CLIENT-ERROR]" in u["logs"]]
    assert len(error_updates) >= 1


@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_network_error(api_client, mock_httpx_client):
    """Tests that a network error is caught and yielded as a status update."""
    mock_client, mock_response = mock_httpx_client
    mock_client.stream.side_effect = httpx.RequestError("Connection refused")

    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    assert len(updates) == 1
    assert "API Error: Connection refused" in updates[0]["status"]


@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_file_read_error(api_client, mock_httpx_client):
    """Tests that an error reading a file is caught and yielded."""
    mock_text_file = MagicMock()
    mock_text_file.name = "bad.txt"
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Permission denied")
        updates = [update async for update in api_client.invoke_agent_streaming("prompt", mock_text_file, None)]

    assert len(updates) == 1
    assert "Error reading file: Permission denied" in updates[0]["status"]
