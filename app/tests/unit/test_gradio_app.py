# app/tests/unit/test_gradio_app.py
import pytest
from unittest.mock import patch, MagicMock
import json

from app.src.ui.gradio_app import invoke_agent
# We patch the ApiClient before importing the app to inject our mock
mock_api_client = MagicMock()

with patch('app.src.ui.gradio_app.ApiClient', return_value=mock_api_client):
    from app.src.ui.gradio_app import create_ui

@pytest.fixture
def mock_requests_post():
    """Mocks requests.post to simulate a streaming API response."""
    with patch('app.src.ui.gradio_app.requests.post') as mock_post:
        yield mock_post
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

def test_invoke_agent_generator(mock_requests_post):
def test_handle_submit_generator(mock_ui_components):
    """
    Tests that the invoke_agent generator correctly processes a stream
    of log events and a final state object.
    Tests that the handle_submit generator correctly processes a stream of
    updates from the ApiClient and yields Gradio update dictionaries.
    """
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"Finished node: router",
        b'FINAL_STATE::{"html_artifact": "<h1>Hello</h1>", "status": "complete"}'
    # This simulates the stream yielded by api_client.invoke_agent_streaming
    mock_stream = [
        {"status": "Processing...", "logs": "Log 1\n"},
        {"logs": "Log 1\nLog 2\n"},
        {"html": "<h1>Result</h1>", "final_state": {"status": "complete"}, "status": "Complete!"}
    ]
    # The context manager `with requests.post(...) as response:` needs to be mocked
    mock_requests_post.return_value.__enter__.return_value = mock_stream_response
    mock_api_client.invoke_agent_streaming.return_value = iter(mock_stream)

    # Mock Gradio components that would be passed in
    # We don't need real components, just placeholders for the dictionary keys
    mock_log_output = "log_output"
    mock_status_output = "status_output"
    mock_json_output = "json_output"
    mock_html_output = "html_output"
    mock_image_output = "image_output"
    # create_ui returns the Gradio Blocks instance. We need to find the
    # handle_submit function that was created inside it.
    # A simple way is to get it from the submit button's click event.
    demo = create_ui(mock_api_client)
    # This is a bit of an introspection hack to get the function
    # bound to the button's click event.
    handle_submit_fn = demo.fns[0][0] # In Gradio, this holds the function

    # Act
    # We consume the generator to get all its yielded values
    generator = invoke_agent("test prompt", None, None)
    generator = handle_submit_fn("test prompt", None, None)
    yielded_updates = list(generator)

    # Assert
    assert len(yielded_updates) == 3 # Two log updates, one final update
    mock_api_client.invoke_agent_streaming.assert_called_once_with("test prompt", None, None)
    assert len(yielded_updates) == 3

    # Check log updates
    assert yielded_updates[0] == {mock_log_output: "Entering node: router\n"}
    assert yielded_updates[1] == {mock_log_output: "Entering node: router\nFinished node: router\n"}

    # Check the final, comprehensive update
    final_update = yielded_updates[2]
    assert final_update[mock_status_output] == "Workflow Complete!"
    assert final_update[mock_html_output] == "<h1>Hello</h1>"
    assert final_update[mock_json_output] == {"html_artifact": "<h1>Hello</h1>", "status": "complete"}
    # Check each yielded UI update dictionary
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Processing...", mock_ui_components["log_output"]: "Log 1\n"}
    assert yielded_updates[1] == {mock_ui_components["log_output"]: "Log 1\nLog 2\n"}
    assert yielded_updates[2] == {mock_ui_components["html_output"]: "<h1>Result</h1>", mock_ui_components["json_output"]: {"status": "complete"}, mock_ui_components["status_output"]: "Complete!"}