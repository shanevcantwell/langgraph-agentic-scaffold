
import pytest
from unittest.mock import patch, MagicMock, call

from app.src.llm.lmstudio_adapter import LMStudioAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import LLMInvocationError
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

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

def test_init_fails_on_missing_api_identifier():
    """Tests that initialization fails if 'api_identifier' is missing from the config."""
    with pytest.raises(TypeError, match="argument of type 'NoneType' is not iterable"):
        LMStudioAdapter(model_config={}, base_url=MOCK_BASE_URL, system_prompt="")

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_sends_correct_request(mock_openai_client, mock_model_config):
    """Tests that the invoke method constructs and sends the correct request to the client."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="You are a helpful assistant.")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
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
    assert result.get('text_response') == "LLM response text"

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_handles_json_parsing(mock_openai_client, mock_model_config):
    """Tests that the invoke method correctly parses JSON from a messy response string."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "Here is the JSON: ```json\n{\"key\": \"value\"}\n```"

    class MockSchema(BaseModel): pass
    request = StandardizedLLMRequest(messages=[], output_model_class=MockSchema)

    # Act
    result = adapter.invoke(request)

    # Assert
    assert result.get('json_response') == {"key": "value"}
    assert result.get('text_response') is None

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_raises_llm_invocation_error(mock_openai_client, mock_model_config):
    """Tests that LLMInvocationError is raised when the client call fails."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.side_effect = Exception("API call failed")

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="LMStudio API error: API call failed"):
        adapter.invoke(request)