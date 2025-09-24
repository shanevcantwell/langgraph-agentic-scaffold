# Audited on Sept 23, 2025
import pytest
from unittest.mock import patch, MagicMock, call
import os

from app.src.llm.lmstudio_adapter import LMStudioAdapter

MOCK_MODEL_NAME = "test-model/test-model-GGUF"
MOCK_BASE_URL = "http://fake-lmstudio:1234/v1"

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mocks environment variables for tests."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", MOCK_BASE_URL)
    monkeypatch.setenv("LMSTUDIO_SSH_HOST", "fake-host")
    monkeypatch.setenv("LMSTUDIO_SSH_USER", "fake-user")
    monkeypatch.setenv("LMSTUDIO_SSH_KEY_PATH", "/fake/path/id_rsa")

@pytest.fixture
def mock_model_config():
    """Provides a basic model configuration."""
    return {"api_identifier": MOCK_MODEL_NAME}

@patch('app.src.llm.lmstudio_adapter.requests.get')
@patch('app.src.llm.lmstudio_adapter.paramiko.SSHClient')
def test_init_success_model_already_loaded(mock_ssh_client, mock_requests_get, mock_model_config):
    """
    Tests successful initialization when the pre-flight API check finds the model is already loaded.
    """
    # Arrange
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"id": MOCK_MODEL_NAME}]}
    mock_requests_get.return_value = mock_response

    # Act
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

    # Assert
    mock_requests_get.assert_called_once_with(f"{MOCK_BASE_URL}/models", timeout=10)
    mock_ssh_client.return_value.connect.assert_not_called() # SSH should not be attempted
    assert adapter.model_name == MOCK_MODEL_NAME

@patch('app.src.llm.lmstudio_adapter.requests.get')
@patch('app.src.llm.lmstudio_adapter.paramiko.SSHClient')
def test_init_success_with_ssh_autoload(mock_ssh_client_cls, mock_requests_get, mock_model_config, mock_env_vars):
    """
    Tests successful initialization where the model is loaded via SSH after the first API check fails.
    """
    # Arrange
    # First API call fails (model not found), second one succeeds
    mock_requests_get.side_effect = [
        MagicMock(json=lambda: {"data": [{"id": "some-other-model"}]}), # Model not loaded
        MagicMock(json=lambda: {"data": [{"id": MOCK_MODEL_NAME}]})      # Model loaded
    ]

    mock_ssh_instance = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 0 # Success exit code
    mock_stdout.read.return_value = b"Model loaded successfully"
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b""
    mock_ssh_instance.exec_command.return_value = (None, mock_stdout, mock_stderr)
    mock_ssh_client_cls.return_value = mock_ssh_instance

    # Act
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

    # Assert
    assert mock_requests_get.call_count == 2
    mock_ssh_instance.connect.assert_called_once_with(
        hostname="fake-host", port=22, username="fake-user", key_filename="/fake/path/id_rsa", timeout=10
    )
    mock_ssh_instance.exec_command.assert_called_once_with(f'lms load "{MOCK_MODEL_NAME}"', timeout=60)
    assert adapter.model_name == MOCK_MODEL_NAME

@patch('app.src.llm.lmstudio_adapter.requests.get')
@patch('app.src.llm.lmstudio_adapter.paramiko.SSHClient')
def test_init_fails_if_ssh_fails(mock_ssh_client_cls, mock_requests_get, mock_model_config, mock_env_vars):
    """
    Tests that initialization raises a RuntimeError if the SSH command fails.
    """
    # Arrange
    mock_requests_get.return_value = MagicMock(json=lambda: {"data": []}) # Model never loads

    mock_ssh_instance = MagicMock()
    mock_stdout = MagicMock()
    mock_stdout.channel.recv_exit_status.return_value = 1 # Failure exit code
    mock_stdout.read.return_value = b""
    mock_stderr = MagicMock()
    mock_stderr.read.return_value = b"Error: model not found"
    mock_ssh_instance.exec_command.return_value = (None, mock_stdout, mock_stderr)
    mock_ssh_client_cls.return_value = mock_ssh_instance

    # Act & Assert
    with pytest.raises(RuntimeError, match="Remote 'lms load' command failed"):
        LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

@patch('app.src.llm.lmstudio_adapter.requests.get')
@patch('app.src.llm.lmstudio_adapter.paramiko.SSHClient')
def test_init_fails_if_model_not_loaded_and_no_ssh_config(mock_ssh_client_cls, mock_requests_get, mock_model_config, monkeypatch):
    """
    Tests that initialization fails gracefully if the model isn't loaded and SSH is not configured.
    """
    # Arrange
    mock_requests_get.return_value = MagicMock(json=lambda: {"data": []})
    # Unset SSH env vars
    monkeypatch.delenv("LMSTUDIO_SSH_HOST", raising=False)
    monkeypatch.delenv("LMSTUDIO_SSH_USER", raising=False)
    monkeypatch.delenv("LMSTUDIO_SSH_KEY_PATH", raising=False)

    # Act & Assert
    with pytest.raises(RuntimeError, match=f"Model '{MOCK_MODEL_NAME}' is not loaded in LM Studio."):
        LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    
    mock_ssh_client_cls.return_value.connect.assert_not_called() # Ensure SSH was not attempted