# Audited on Sept 23, 2025
import pytest
from unittest.mock import patch, MagicMock, call
import os

from app.src.llm.lmstudio_adapter import LMStudioAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import LLMInvocationError
from langchain_core.messages import HumanMessage

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
    return {
        "api_identifier": MOCK_MODEL_NAME,
        "parameters": {"temperature": 0.7}
    }

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

@patch('app.src.llm.lmstudio_adapter.requests.get')
def test_init_fails_on_api_connection_error(mock_requests_get, mock_model_config):
    """Tests that initialization fails if the pre-flight check to the API fails."""
    # Arrange
    mock_requests_get.side_effect = Exception("Connection timed out")

    # Act & Assert
    with pytest.raises(RuntimeError, match="Could not connect to LM Studio server"):
        LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

def test_init_fails_on_missing_api_identifier():
    """Tests that initialization fails if 'api_identifier' is missing from the config."""
    with pytest.raises(ValueError, match="is missing required parameter: 'api_identifier'"):
        LMStudioAdapter(model_config={}, base_url=MOCK_BASE_URL, system_prompt="")

@patch('app.src.llm.lmstudio_adapter.OpenAI')
@patch('app.src.llm.lmstudio_adapter.LMStudioAdapter._perform_pre_flight_checks')
def test_invoke_sends_correct_request(mock_pre_flight, mock_openai_client, mock_model_config):
    """Tests that the invoke method constructs and sends the correct request to the client."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="You are a helpful assistant.")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.content = "LLM response text"

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello, world!")])

    # Act
    result = adapter.invoke(request)

    # Assert
    mock_create.assert_called_once()
    call_args, call_kwargs = mock_create.call_args
    
    # Check messages payload
    sent_messages = call_kwargs['messages']
    assert len(sent_messages) == 2
    assert sent_messages[0]['role'] == 'system'
    assert sent_messages[0]['content'] == 'You are a helpful assistant.'
    assert sent_messages[1]['role'] == 'user'
    assert sent_messages[1]['content'] == 'Hello, world!'

    # Check other parameters
    assert call_kwargs['model'] == MOCK_MODEL_NAME
    assert call_kwargs['temperature'] == 0.7
    assert result['text_response'] == "LLM response text"

@patch('app.src.llm.lmstudio_adapter.OpenAI')
@patch('app.src.llm.lmstudio_adapter.LMStudioAdapter._perform_pre_flight_checks')
def test_invoke_handles_json_parsing(mock_pre_flight, mock_openai_client, mock_model_config):
    """Tests that the invoke method correctly parses JSON from a messy response string."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.content = "Here is the JSON: ```json\n{\"key\": \"value\"}\n```"

    class MockSchema(MagicMock): pass
    request = StandardizedLLMRequest(messages=[], output_model_class=MockSchema)

    # Act
    result = adapter.invoke(request)

    # Assert
    assert result['json_response'] == {"key": "value"}
    assert result.get('text_response') is None

@patch('app.src.llm.lmstudio_adapter.OpenAI')
@patch('app.src.llm.lmstudio_adapter.LMStudioAdapter._perform_pre_flight_checks')
def test_invoke_raises_llm_invocation_error(mock_pre_flight, mock_openai_client, mock_model_config):
    """Tests that LLMInvocationError is raised when the client call fails."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.side_effect = Exception("API call failed")

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="Error invoking LM Studio model"):
        adapter.invoke(request)