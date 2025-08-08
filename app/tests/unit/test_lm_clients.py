import pytest
from unittest.mock import patch, MagicMock
from src.llm.clients import LMStudioClient, OllamaClient
from langchain_core.messages import HumanMessage, AIMessage

@patch('requests.post')
def test_lmstudio_client_invoke(mock_post):
    """Tests that the LMStudioClient correctly formats the payload and parses the response."""
    client = LMStudioClient(model="test-model", base_url="http://fake-url:1234/v1")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"response": "Hello from LM Studio"}'
                }
            }
        ]
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    messages = [HumanMessage(content="Hello")]
    response = client.invoke(messages, temperature=0.5)

    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    
    # Check URL
    assert call_args[0] == "http://fake-url:1234/v1/chat/completions"
    
    # Check payload
    payload = call_kwargs['json']
    assert payload['model'] == "test-model"
    assert payload['temperature'] == 0.5
    assert payload['messages'] == [{"role": "user", "content": "Hello"}]

    # Check response
    assert isinstance(response, AIMessage)
    assert response.content == '{"response": "Hello from LM Studio"}'

@patch('requests.post')
def test_ollama_client_invoke(mock_post):
    """Tests that the OllamaClient correctly formats the payload and parses the response."""
    client = OllamaClient(model="test-ollama", base_url="http://fake-ollama:11434")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "message": {
            "role": "assistant",
            "content": '{"response": "Hello from Ollama"}'
        }
    }
    mock_response.raise_for_status = MagicMock()
    mock_post.return_value = mock_response

    messages = [HumanMessage(content="Hello")]
    response = client.invoke(messages, temperature=0.5)

    mock_post.assert_called_once()
    call_args, call_kwargs = mock_post.call_args
    
    assert call_args[0] == "http://fake-ollama:11434/api/chat"
    
    payload = call_kwargs['json']
    assert payload['model'] == "test-ollama"
    assert payload['options']['temperature'] == 0.5
    assert payload['messages'] == [{"role": "user", "content": "Hello"}]

    assert isinstance(response, AIMessage)
    assert response.content == '{"response": "Hello from Ollama"}'