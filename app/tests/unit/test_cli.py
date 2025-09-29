# app/tests/unit/test_cli.py
import pytest
import json
import requests
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from app.src.cli import app

runner = CliRunner()

@pytest.fixture
def mock_requests():
    """Mocks the requests library to prevent actual HTTP calls."""
    with patch("app.src.cli.requests.post") as mock_post:
        yield mock_post

def test_cli_invoke_success(mock_requests):
    """Tests the 'invoke' command with a successful API response."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "final_output": {"artifacts": {"final_user_response.md": "Success!"}}
    }
    mock_requests.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Final Response" in result.stdout
    assert "Success!" in result.stdout
    mock_requests.assert_called_once()

def test_cli_invoke_json_only(mock_requests):
    """Tests the 'invoke' command with the --json-only flag."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"final_output": {"artifacts": {"final_user_response.md": "Success!"}}}
    mock_requests.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "test prompt", "--json-only"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Final Response" not in result.stdout # Suppressed messages
    assert '"final_user_response.md": "Success!"' in result.stdout # Just the JSON

def test_cli_stream_success(mock_requests):
    """Tests the 'stream' command with a successful streaming response."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"FINAL_STATE::{\"status\": \"stream complete\", \"artifacts\": {\"final_user_response.md\": \"Success!\"}}"
    ]
    # The context manager `with requests.post(...) as response:` needs to be mocked
    mock_requests.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test stream prompt"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Log Stream" in result.stdout
    assert "Entering node: router" in result.stdout
    # The final JSON is always printed for scripting, with the prefix stripped
    assert result.stdout.strip().endswith('{"status": "stream complete", "artifacts": {"final_user_response.md": "Success!"}}')

def test_cli_invoke_api_non_200_response(mock_requests):
    """Tests how the CLI handles a non-200 status code from the API."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"final_output": {"error_report": "Internal Server Error"}}
    mock_requests.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "Agent Workflow Failed" in result.stdout

def test_cli_api_error(mock_requests):
    """Tests that the CLI handles API connection errors gracefully."""
    # Arrange
    # Simulate a network-level failure by having the post call raise an exception.
    mock_requests.side_effect = requests.exceptions.RequestException("Connection failed")

    # Act
    # Let the CLI's internal error handling catch the exception.
    # We then verify that it printed the correct error message and exited with status 1.
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "Could not connect to the API server" in result.stderr
def test_cli_stream_no_final_state(mock_requests):
    """Tests the stream command when the FINAL_STATE line is missing."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"Some other log line"
    ]
    mock_requests.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test prompt"])

    # Assert
    assert result.exit_code == 1 # Verification should fail
    assert "Stream completed without a FINAL_STATE message" in result.stderr

def test_cli_stream_malformed_final_state_json(mock_requests):
    """Tests the stream command when the FINAL_STATE JSON is malformed."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [b"FINAL_STATE::{'invalid-json'}", b"some other line"] # type: ignore
    mock_requests.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test prompt"])

    # Assert
    assert result.exit_code == 1 # Verification should fail
    assert "Failed to parse FINAL_STATE JSON" in result.stderr

def test_cli_invoke_no_prompt():
    """Tests that the 'invoke' command exits with an error if no prompt is provided."""
    # With the new structure, invoking without a prompt reads from stdin.
    # An empty stdin should result in an exit code of 1 from our logic.
    result = runner.invoke(app, ["invoke"], input="")
    assert result.exit_code == 1
    assert "Error: Prompt is empty." in result.stderr

def test_cli_stream_no_prompt():
    """Tests that the 'stream' command exits with an error if no prompt is provided."""
    result = runner.invoke(app, ["stream"], input="")
    assert result.exit_code == 1
    assert "Error: Prompt is empty." in result.stderr