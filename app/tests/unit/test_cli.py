# Audited on Sept 23, 2025
# app/tests/unit/test_cli.py
import pytest
import json
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner

from app.src.cli import app

runner = CliRunner()

@pytest.fixture
def mock_requests():
    """Mocks the requests library to prevent actual HTTP calls."""
    with patch("app.src.cli.requests") as mock_requests_patch:
        yield mock_requests_patch

def test_cli_invoke_success(mock_requests):
    """Tests the 'invoke' command with a successful API response."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"final_output": {"status": "complete"}}
    mock_requests.post.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Final Response" in result.stdout
    assert '"status": "complete"' in result.stdout
    mock_requests.post.assert_called_once()

def test_cli_invoke_json_only(mock_requests):
    """Tests the 'invoke' command with the --json-only flag."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"final_output": {"status": "complete"}}
    mock_requests.post.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "--json-only", "test prompt"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Final Response" not in result.stdout # Suppressed messages
    assert '{\n  "status": "complete"\n}' in result.stdout # Just the JSON

def test_cli_stream_success(mock_requests):
    """Tests the 'stream' command with a successful streaming response."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"FINAL_STATE::{\"status\": \"stream complete\"}"
    ]
    # The context manager `with requests.post(...) as response:` needs to be mocked
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test stream prompt"])

    # Assert
    assert result.exit_code == 0
    assert "Agent Log Stream" in result.stdout
    assert "Entering node: router" in result.stdout
    assert "End of Stream" in result.stdout
    # The final JSON is always printed for scripting
    assert '{"status": "stream complete"}' in result.stdout

def test_cli_invoke_api_non_200_response(mock_requests):
    """Tests how the CLI handles a non-200 status code from the API."""
    # Arrange
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_requests.post.return_value = mock_response

    # Act
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "API request failed with status 500" in result.stdout

def test_cli_api_error(mock_requests):
    """Tests that the CLI handles API connection errors gracefully."""
    # Arrange
    mock_requests.post.side_effect = requests.exceptions.RequestException("Connection failed")

    # Act
    result = runner.invoke(app, ["invoke", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "Error: Could not connect to the API server" in result.stdout

def test_cli_stream_no_final_state(mock_requests):
    """Tests the stream command when the FINAL_STATE line is missing."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [
        b"Entering node: router",
        b"Some other log line"
    ]
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "Stream completed without a FINAL_STATE message" in result.stdout

def test_cli_stream_malformed_final_state_json(mock_requests):
    """Tests the stream command when the FINAL_STATE JSON is malformed."""
    # Arrange
    mock_stream_response = MagicMock()
    mock_stream_response.iter_lines.return_value = [b"FINAL_STATE::{'invalid-json'}"]
    mock_requests.post.return_value.__enter__.return_value = mock_stream_response

    # Act
    result = runner.invoke(app, ["stream", "test prompt"])

    # Assert
    assert result.exit_code == 1
    assert "Failed to parse FINAL_STATE JSON" in result.stdout