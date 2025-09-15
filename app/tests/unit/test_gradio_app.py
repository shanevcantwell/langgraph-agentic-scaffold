# app/tests/unit/test_gradio_app.py
import pytest
from unittest.mock import patch, MagicMock
import json

from app.src.ui.gradio_app import invoke_agent

@pytest.fixture
def mock_requests_post():
    """Mocks requests.post to simulate a streaming API response."""
    with patch('app.src.ui.gradio_app.requests.post') as mock_post:
        yield mock_post

def test_invoke_agent_generator(mock_requests_post):
    """
    Tests that the invoke_agent generator correctly processes a stream
    of log events and a final state object.
    """
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"Finished node: router",
        b'FINAL_STATE::{"html_artifact": "<h1>Hello</h1>", "status": "complete"}'
    ]
    # The context manager `with requests.post(...) as response:` needs to be mocked
    mock_requests_post.return_value.__enter__.return_value = mock_stream_response

    # Mock Gradio components that would be passed in
    # We don't need real components, just placeholders for the dictionary keys
    mock_log_output = "log_output"
    mock_status_output = "status_output"
    mock_json_output = "json_output"
    mock_html_output = "html_output"
    mock_image_output = "image_output"

    # Act
    # We consume the generator to get all its yielded values
    generator = invoke_agent("test prompt", None, None)
    yielded_updates = list(generator)

    # Assert
    assert len(yielded_updates) == 3 # Two log updates, one final update

    # Check log updates
    assert yielded_updates[0] == {mock_log_output: "Entering node: router\n"}
    assert yielded_updates[1] == {mock_log_output: "Entering node: router\nFinished node: router\n"}

    # Check the final, comprehensive update
    final_update = yielded_updates[2]
    assert final_update[mock_status_output] == "Workflow Complete!"
    assert final_update[mock_html_output] == "<h1>Hello</h1>"
    assert final_update[mock_json_output] == {"html_artifact": "<h1>Hello</h1>", "status": "complete"}