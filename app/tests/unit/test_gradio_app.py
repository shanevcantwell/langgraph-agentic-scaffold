# app/tests/unit/test_gradio_app.py
import pytest
from unittest.mock import patch, MagicMock

# We patch the ApiClient before importing the app to inject our mock
mock_api_client = MagicMock()

with patch('app.src.ui.gradio_app.ApiClient', return_value=mock_api_client):
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

def test_handle_submit_generator(mock_ui_components):
    """
    Tests that the handle_submit generator correctly processes a stream of
    updates from the ApiClient and yields Gradio update dictionaries.
    """
    # Arrange
    # This simulates the stream yielded by api_client.invoke_agent_streaming
    mock_stream = [
        {"status": "Processing...", "logs": "Log 1\n"},
        {"logs": "Log 1\nLog 2\n"},
        {"html": "<h1>Result</h1>", "final_state": {"status": "complete"}, "status": "Complete!"}
    ]
    mock_api_client.invoke_agent_streaming.return_value = iter(mock_stream)

    # create_ui returns the Gradio Blocks instance. We need to find the
    # handle_submit function that was created inside it.
    # A simple way is to get it from the submit button's click event.
    demo = create_ui(mock_api_client)
    # This is a bit of an introspection hack to get the function
    # bound to the button's click event.
    handle_submit_fn = demo.fns[0][0] # In Gradio, this holds the function

    # Act
    generator = handle_submit_fn("test prompt", None, None)
    yielded_updates = list(generator)

    # Assert
    mock_api_client.invoke_agent_streaming.assert_called_once_with("test prompt", None, None)
    assert len(yielded_updates) == 3

    # Check each yielded UI update dictionary
    assert yielded_updates[0] == {mock_ui_components["status_output"]: "Processing...", mock_ui_components["log_output"]: "Log 1\n"}
    assert yielded_updates[1] == {mock_ui_components["log_output"]: "Log 1\nLog 2\n"}
    assert yielded_updates[2] == {mock_ui_components["html_output"]: "<h1>Result</h1>", mock_ui_components["json_output"]: {"status": "complete"}, mock_ui_components["status_output"]: "Complete!"}