# app/tests/unit/test_api_client.py
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
    Mocks the httpx.AsyncClient to prevent actual HTTP calls. This is a complex
    mock because it involves mocking a nested async context manager.
    The key is to mock the `__aenter__` and `__aexit__` methods of the
    objects that are used in `async with` statements.
    """
    mock_client_instance = AsyncMock(spec=httpx.AsyncClient)
    mock_response = AsyncMock(spec=httpx.Response)

    # Mock the context manager for the client
    mock_client_cm = AsyncMock()
    mock_client_cm.__aenter__.return_value = mock_client_instance

    # Mock the context manager for the stream response
    mock_response_cm = AsyncMock()
    mock_response_cm.__aenter__.return_value = mock_response
    mock_client_instance.stream.return_value = mock_response_cm

    with patch("app.src.ui.api_client.httpx.AsyncClient", return_value=mock_client_cm):
        yield mock_client_instance, mock_response

def test_encode_image_to_base64(api_client):
    """Tests the internal image encoding utility."""
    # Arrange
    mock_image_data = b"fake_image_bytes"
    expected_base64 = base64.b64encode(mock_image_data).decode('utf-8')
    
    with patch("builtins.open", mock_open(read_data=mock_image_data)) as mock_file:
        # Act
        result = api_client._encode_image_to_base64("fake_path.jpg")
        
        # Assert
        mock_file.assert_called_once_with("fake_path.jpg", "rb")
        assert result == expected_base64

@pytest.mark.asyncio
async def test_invoke_agent_streaming_success(api_client, mock_httpx_client):
    """Tests the happy path for streaming, parsing, and yielding updates."""
    # Arrange
    mock_client, mock_response = mock_httpx_client

    async def stream_generator():
        yield 'data: {"status": "Processing..."}'
        yield 'data: {"logs": "Log 1"}'
        yield 'data: {"final_state": {"status": "complete"}, "html": "<h1>Hello</h1>", "archive": "Report"}'

    mock_response.aiter_lines.return_value = stream_generator()

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test prompt", None, None)]

    # Assert
    assert len(updates) == 4 # 3 from stream, 1 final empty block
    assert updates[0] == {"status": "Processing..."}
    assert updates[1] == {"logs": "Log 1"}
    assert updates[2] == {"final_state": {"status": "complete"}, "html": "<h1>Hello</h1>", "archive": "Report"}
    # The last update is the final empty block from the client
    assert updates[3]["final_state"] == {}

    # Verify the mock was called correctly
    mock_client.stream.assert_called_once_with(
        "POST", "http://127.0.0.1:8000/v1/graph/stream", json={'input_prompt': 'test prompt'}
    )

@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_file_and_image(api_client, mock_httpx_client):
    """Tests that text files and images are correctly read and encoded in the payload."""
    # Arrange
    mock_client, mock_response = mock_httpx_client
    async def empty_gen():
        if False: yield
    mock_response.aiter_lines.return_value = empty_gen()
    
    # Mock file objects that have a 'name' attribute
    mock_text_file = MagicMock()
    mock_text_file.name = "test.txt"
    mock_image_file = MagicMock()
    mock_image_file.name = "test.png"

    # Mock `open` to handle different files and modes
    def mock_open_logic(file, mode='r', **kwargs):
        if file == "test.txt":
            return mock_open(read_data="file content").return_value
        if file == "test.png":
            return mock_open(read_data=b"image bytes").return_value
        return mock_open().return_value # Default mock

    with patch("builtins.open", side_effect=mock_open_logic):
        _ = [update async for update in api_client.invoke_agent_streaming("prompt", mock_text_file, mock_image_file)]

    # Assert
    mock_client.stream.assert_called_once()
    sent_payload = mock_client.stream.call_args[1]['json']
    assert sent_payload["input_prompt"] == "prompt"
    assert sent_payload["text_to_process"] == "file content"
    assert sent_payload["image_to_process"] == base64.b64encode(b"image bytes").decode('utf-8')

@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_malformed_json(api_client, mock_httpx_client):
    """Tests robust error handling when the FINAL_STATE JSON is invalid."""
    # Arrange
    mock_client, mock_response = mock_httpx_client
    malformed_json_str = "data: {'invalid-json':,}"
    async def gen():
        yield malformed_json_str
    mock_response.aiter_lines.return_value = gen()

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    # The error is logged, and the final empty block is also yielded.
    assert len(updates) == 2
    assert "[UI-CLIENT-ERROR]" in updates[0]["logs"]
    assert "Failed to parse JSON" in updates[0]["logs"]

@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_image_decoding(api_client, mock_httpx_client):
    """Tests that a base64 image artifact is correctly decoded into a PIL Image."""
    # Arrange
    mock_client, mock_response = mock_httpx_client
    # Create a dummy 1x1 pixel black image
    img = Image.new('RGB', (1, 1), color = 'black')
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    # The image artifact is no longer handled by the client, but by the UI.
    # This test now verifies that if an image artifact were sent in the stream,
    # it would be yielded correctly.
    async def stream_generator():
        yield f'data: {json.dumps({"image_artifact_b64": img_b64})}'
    mock_response.aiter_lines.return_value = stream_generator()

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    # The client's only job is to yield the data it receives.
    assert len(updates) == 2 # 1 from stream, 1 final empty block
    assert updates[0] == {"image_artifact_b64": img_b64}

@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_network_error(api_client, mock_httpx_client):
    """Tests that a RequestException is caught and yielded as a status update."""
    # Arrange
    mock_client, mock_response = mock_httpx_client
    mock_client.stream.side_effect = httpx.RequestError("Connection refused")

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    assert len(updates) == 1
    error_update = updates[0]
    assert "API Error: Connection refused" in error_update["status"]
    assert "ERROR: Connection refused" in error_update["logs"]

@pytest.mark.asyncio
async def test_invoke_agent_streaming_handles_file_read_error(api_client, mock_httpx_client):
    """Tests that an error reading a file is caught and yielded."""
    # Arrange
    mock_text_file = MagicMock()
    mock_text_file.name = "bad.txt"
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Permission denied")
        updates = [update async for update in api_client.invoke_agent_streaming("prompt", mock_text_file, None)]

    assert len(updates) == 1
    assert "Error reading file: Permission denied" in updates[0]["status"]