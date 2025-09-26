# app/tests/unit/test_api_client.py
import pytest
from unittest.mock import patch, MagicMock, mock_open
import base64
import json
from PIL import Image
import io

from app.src.ui.api_client import ApiClient

@pytest.fixture
def api_client():
    """Provides an instance of the ApiClient."""
    return ApiClient()

@pytest.fixture
def mock_requests():
    """Mocks the requests library to prevent actual HTTP calls."""
    with patch("app.src.ui.api_client.requests") as mock_requests_patch:
        yield mock_requests_patch

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

async def test_invoke_agent_streaming_success(api_client, mock_requests):
    """Tests the happy path for streaming, parsing, and yielding updates."""
    # Arrange
    final_state = {
        "artifacts": {
            "html_document.html": "<h1>Hello</h1>",
            "archive_report.md": "Report content"
        }
    }
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Log line 1",
        b"Log line 2",
        f"FINAL_STATE::{json.dumps(final_state)}".encode('utf-8')
    ]
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test prompt", None, None)]

    # Assert
    assert len(updates) == 3 # Two log updates, one final update
    assert updates[0] == {"logs": "Log line 1\n"}
    assert updates[1] == {"logs": "Log line 1\nLog line 2\n"}
    
    final_update = updates[2]
    assert final_update["status"] == "Workflow Complete!"
    assert final_update["final_state"] == final_state
    assert final_update["html"] == "<h1>Hello</h1>"
    assert final_update["archive"] == "Report content"

async def test_invoke_agent_streaming_handles_file_and_image(api_client, mock_requests):
    """Tests that text files and images are correctly read and encoded in the payload."""
    # Arrange
    mock_requests.post.return_value.__enter__.return_value.iter_lines.return_value = []
    
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
    mock_requests.post.assert_called_once()
    sent_payload = mock_requests.post.call_args[1]['json']
    assert sent_payload["input_prompt"] == "prompt"
    assert sent_payload["text_to_process"] == "file content"
    assert sent_payload["image_to_process"] == base64.b64encode(b"image bytes").decode('utf-8')

async def test_invoke_agent_streaming_handles_malformed_json(api_client, mock_requests):
    """Tests robust error handling when the FINAL_STATE JSON is invalid."""
    # Arrange
    malformed_json_str = "FINAL_STATE::{'invalid-json':,}"
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [malformed_json_str.encode('utf-8')]
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    assert len(updates) == 1
    error_update = updates[0]
    assert error_update["status"] == "Error: Received invalid JSON from backend."
    assert "JSON Parsing Error" in error_update["final_state"]
    assert error_update["final_state"]["Received Malformed String"] == "{'invalid-json':,}"

async def test_invoke_agent_streaming_handles_image_decoding(api_client, mock_requests):
    """Tests that a base64 image artifact is correctly decoded into a PIL Image."""
    # Arrange
    # Create a dummy 1x1 pixel black image
    img = Image.new('RGB', (1, 1), color = 'black')
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

    final_state = {"artifacts": {"image_artifact_b64": img_b64}}
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [f"FINAL_STATE::{json.dumps(final_state)}".encode('utf-8')]
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    assert len(updates) == 1
    final_update = updates[0]
    assert isinstance(final_update["image"], Image.Image)
    assert final_update["image"].size == (1, 1)
async def test_invoke_agent_streaming_handles_network_error(api_client, mock_requests):
    """Tests that a RequestException is caught and yielded as a status update."""
    # Arrange
    from requests.exceptions import RequestException
    mock_requests.post.side_effect = RequestException("Connection refused")

    # Act
    updates = [update async for update in api_client.invoke_agent_streaming("test", None, None)]

    # Assert
    assert len(updates) == 1
    error_update = updates[0]
    assert "API Error: Connection refused" in error_update["status"]
    assert "ERROR: Connection refused" in error_update["logs"]
async def test_invoke_agent_streaming_handles_file_read_error(api_client, mock_requests):
    """Tests that an error reading a file is caught and yielded."""
    # Arrange
    mock_text_file = MagicMock()
    mock_text_file.name = "bad.txt"
    with patch("builtins.open", mock_open()) as mock_file:
        mock_file.side_effect = IOError("Permission denied")
        updates = [update async for update in api_client.invoke_agent_streaming("prompt", mock_text_file, None)]

    assert len(updates) == 1
    assert "Error reading file: Permission denied" in updates[0]["status"]