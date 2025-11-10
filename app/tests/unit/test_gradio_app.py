# app/tests/unit/test_gradio_app.py
from unittest.mock import patch, MagicMock, AsyncMock
import gradio as gr

# We patch the ApiClient class before importing the app to inject our mock.
# The mock will be an instance of MagicMock.
mock_api_client = MagicMock() 
# The method `invoke_agent_streaming` is an async generator. We'll set its
# return value inside each test.
with patch('app.src.ui.api_client.ApiClient', return_value=mock_api_client):
    # We import the function that contains the logic, not the whole app
    from app.src.ui.gradio_app import handle_submit

import pytest

@pytest.fixture
def mock_ui_components():
    """Mocks Gradio components to be used as dictionary keys."""
    # In tests, we can use simple strings or objects as stand-ins for the
    # actual Gradio component objects, since they are just used as keys.
    return {key: MagicMock(name=key) for key in [
        "status_output", "log_output", "json_output", "html_output",
        "image_output", "archive_output"
    ]}

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
    def mock_stream_generator(*args, **kwargs):
        yield {"status": "Processing...", "logs": "Log 1\n"}
        yield {"logs": "Log 1\nLog 2\n"}
        yield {"html": "<h1>Result</h1>", "final_state": {"status": "complete"}, "status": "Complete!"}

    # The mock needs to return an async generator
    async def mock_async_gen(*args, **kwargs):
        for item in mock_stream_generator():
            yield item # This makes it an async generator
    mock_api_client.invoke_agent_streaming.return_value = mock_async_gen() # The method returns the generator
    
    # The handle_submit function returns a closure, which is our test subject
    handle_submit_fn = handle_submit(
        mock_api_client, **mock_ui_components
    )

    # Act
    # The closure returns an async generator, which we consume.
    yielded_updates = [item async for item in handle_submit_fn("test prompt", None, None, False)]

    # Assert
    mock_api_client.invoke_agent_streaming.assert_called_once_with("test prompt", None, None, False)
    assert len(yielded_updates) == 3
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Processing...", mock_ui_components["log_output"]: "Log 1\n"} # First yield
    assert yielded_updates[1] == {mock_ui_components["log_output"]: "Log 1\nLog 2\n"} # Second yield
    
    # The HTML content is now wrapped in an iframe for sandboxing.
    expected_iframe = f'<iframe srcdoc="&lt;h1&gt;Result&lt;/h1&gt;" style="width: 100%; height: 600px; border: none;"></iframe>'
    assert yielded_updates[2] == {
        mock_ui_components["status_output"]: "Complete!",
        mock_ui_components["json_output"]: {"status": "complete"},
        mock_ui_components["html_output"]: gr.update(value=expected_iframe, visible=True)
    }

@pytest.mark.asyncio
async def test_handle_submit_handles_api_error(mock_ui_components):
    """Tests that handle_submit yields an error message if the API client fails."""
    # Arrange
    def mock_fail_generator(*args, **kwargs):
        # This simulates how the api_client would yield an error
        yield {"status": "API Error: API Connection Failed"}

    async def mock_async_gen(*args, **kwargs):
        for item in mock_fail_generator():
            yield item # This makes it an async generator
    mock_api_client.invoke_agent_streaming.return_value = mock_async_gen() # The method returns the generator

    handle_submit_fn = handle_submit(
        mock_api_client, **mock_ui_components
    )

    # Act
    yielded_updates = [item async for item in handle_submit_fn("test prompt", None, None, False)]

    # Assert
    assert len(yielded_updates) == 1
    update = yielded_updates[0]
    assert "API Error" in update[mock_ui_components["status_output"]]
    assert "API Connection Failed" in update[mock_ui_components["status_output"]]

@pytest.mark.asyncio
async def test_handle_submit_handles_all_output_types(mock_ui_components):
    """Tests that all possible output types from the stream are handled."""
    # Arrange
    def mock_stream_generator(*args, **kwargs):
        yield {"image": "path/to/image.png", "archive": "path/to/archive.zip"}

    async def mock_async_gen(*args, **kwargs):
        for item in mock_stream_generator():
            yield item # This makes it an async generator
    mock_api_client.invoke_agent_streaming.return_value = mock_async_gen() # The method returns the generator

    handle_submit_fn = handle_submit(
        mock_api_client, **mock_ui_components
    )

    # Act
    yielded_updates = [item async for item in handle_submit_fn("test prompt", None, None, False)]

    # Assert
    assert len(yielded_updates) == 1
    update = yielded_updates[0]
    assert update[mock_ui_components["image_output"]] == gr.update(value="path/to/image.png", visible=bool("path/to/image.png"))
    assert update[mock_ui_components["archive_output"]] == "path/to/archive.zip"

@pytest.mark.asyncio
async def test_handle_submit_handles_empty_stream_data(mock_ui_components):
    """Tests that empty or malformed data in the stream is ignored gracefully."""
    # Arrange
    def mock_stream_generator(*args, **kwargs):
        yield {}  # Empty dict
        yield {"unknown_key": "some_value"} # Unknown key
        yield {"status": "Still working..."}

    async def mock_async_gen(*args, **kwargs):
        for item in mock_stream_generator():
            yield item # This makes it an async generator
    mock_api_client.invoke_agent_streaming.return_value = mock_async_gen() # The method returns the generator

    handle_submit_fn = handle_submit(
        mock_api_client, **mock_ui_components
    )

    # Act
    yielded_updates = [item async for item in handle_submit_fn("test prompt", None, None, False)]

    # Assert
    # The first two yields should produce empty dicts, which are filtered out.
    # Only the valid update should be yielded.
    assert len(yielded_updates) == 1
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Still working..."}

@pytest.mark.asyncio
async def test_handle_submit_with_no_prompt(mock_ui_components):
    """Tests that submitting with no prompt does not call the API."""
    # Arrange
    handle_submit_fn = handle_submit(
        mock_api_client, **mock_ui_components
    )

    # Act
    yielded_updates = [item async for item in handle_submit_fn("", None, None, False)]

    # Assert
    mock_api_client.invoke_agent_streaming.assert_not_called()
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Please enter a prompt."}