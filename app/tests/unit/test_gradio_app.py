# Audit Date: Sept 23, 2025
# app/tests/unit/test_gradio_app.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import gradio as gr

# We patch the ApiClient before importing the app to inject our mock
mock_api_client = MagicMock()
# The API client's method is async, so we need to mock it with an AsyncMock
mock_api_client.invoke_agent_streaming = AsyncMock()

with patch('app.src.ui.api_client.ApiClient', return_value=mock_api_client):
    from app.src.ui.gradio_app import create_ui

@pytest.fixture
def mock_ui_components():
    """Mocks Gradio components to be used as dictionary keys."""
    return {
        "status_output": MagicMock(),
        "log_output": MagicMock(),
        "json_output": MagicMock(),
        "html_output": MagicMock(),
        "image_output": MagicMock(),
        "archive_output": MagicMock(),
    }

@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset mocks before each test to ensure isolation."""
    mock_api_client.reset_mock()
    mock_api_client.invoke_agent_streaming.reset_mock()

@pytest.mark.asyncio
async def test_handle_submit_processes_stream_correctly(mock_ui_components):
    """
    Tests that the handle_submit generator correctly processes a stream of
    updates from the ApiClient and yields Gradio update dictionaries.
    """
    # Arrange
    async def mock_stream_generator():
        yield {"status": "Processing...", "logs": "Log 1\n"}
        yield {"logs": "Log 1\nLog 2\n"}
        yield {"html": "<h1>Result</h1>", "final_state": {"status": "complete"}, "status": "Complete!"}

    mock_api_client.invoke_agent_streaming.return_value = mock_stream_generator()

    demo = create_ui(mock_api_client)
    handle_submit_fn = demo.fns[0][0]

    # Act
    yielded_updates = [update async for update in handle_submit_fn("test prompt", None, None)]

    # Assert
    mock_api_client.invoke_agent_streaming.assert_called_once_with("test prompt", None, None)
    assert len(yielded_updates) == 3
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Processing...", mock_ui_components["log_output"]: "Log 1\n"}
    assert yielded_updates[1] == {mock_ui_components["log_output"]: "Log 1\nLog 2\n"}
    assert yielded_updates[2] == {mock_ui_components["html_output"]: "<h1>Result</h1>", mock_ui_components["json_output"]: {"status": "complete"}, mock_ui_components["status_output"]: "Complete!"}

@pytest.mark.asyncio
async def test_handle_submit_handles_api_error(mock_ui_components):
    """Tests that handle_submit yields an error message if the API client fails."""
    # Arrange
    mock_api_client.invoke_agent_streaming.side_effect = Exception("API Connection Failed")
    demo = create_ui(mock_api_client)
    handle_submit_fn = demo.fns[0][0]

    # Act
    yielded_updates = [update async for update in handle_submit_fn("test prompt", None, None)]

    # Assert
    assert len(yielded_updates) == 1
    error_update = yielded_updates[0]
    assert "Error" in error_update[mock_ui_components["status_output"]]
    assert "API Connection Failed" in error_update[mock_ui_components["status_output"]]

@pytest.mark.asyncio
async def test_handle_submit_handles_all_output_types(mock_ui_components):
    """Tests that all possible output types from the stream are handled."""
    # Arrange
    async def mock_stream_generator():
        yield {"image": "path/to/image.png", "archive": "path/to/archive.zip"}

    mock_api_client.invoke_agent_streaming.return_value = mock_stream_generator()
    demo = create_ui(mock_api_client)
    handle_submit_fn = demo.fns[0][0]

    # Act
    yielded_updates = [update async for update in handle_submit_fn("test prompt", None, None)]

    # Assert
    assert len(yielded_updates) == 1
    update = yielded_updates[0]
    assert update[mock_ui_components["image_output"]] == gr.update(value="path/to/image.png", visible=True)
    assert update[mock_ui_components["archive_output"]] == gr.update(value="path/to/archive.zip", visible=True)

@pytest.mark.asyncio
async def test_handle_submit_handles_empty_stream_data(mock_ui_components):
    """Tests that empty or malformed data in the stream is ignored gracefully."""
    # Arrange
    async def mock_stream_generator():
        yield {}  # Empty dict
        yield {"unknown_key": "some_value"} # Unknown key
        yield {"status": "Still working..."}

    mock_api_client.invoke_agent_streaming.return_value = mock_stream_generator()
    demo = create_ui(mock_api_client)
    handle_submit_fn = demo.fns[0][0]

    # Act
    yielded_updates = [update async for update in handle_submit_fn("test prompt", None, None)]

    # Assert
    # The first two yields should produce empty dicts, which are filtered out.
    # Only the valid update should be yielded.
    assert len(yielded_updates) == 1
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Still working..."}

@pytest.mark.asyncio
async def test_handle_submit_with_no_prompt(mock_ui_components):
    """Tests that submitting with no prompt does not call the API."""
    # Arrange
    demo = create_ui(mock_api_client)
    handle_submit_fn = demo.fns[0][0]

    # Act
    yielded_updates = [update async for update in handle_submit_fn("", None, None)]

    # Assert
    mock_api_client.invoke_agent_streaming.assert_not_called()
    assert len(yielded_updates) == 0