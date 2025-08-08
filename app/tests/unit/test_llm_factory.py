import pytest
from unittest.mock import patch
from src.llm.factory import LLMClientFactory
from src.llm.clients import GeminiClient, OllamaClient, LMStudioClient

@pytest.fixture(autouse=True)
def clear_factory_instances():
    """Fixture to clear the LLMClientFactory instances before each test."""
    LLMClientFactory._instances = {}
    yield
    LLMClientFactory._instances = {}

@patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'})
def test_factory_creates_gemini_singleton(mocker):
    """Tests that the factory creates only one instance of a Gemini client."""
    mocker.patch('src.llm.clients.GeminiClient.__init__', return_value=None)
    
    client1 = LLMClientFactory.create_client("gemini")
    client2 = LLMClientFactory.create_client("gemini")

    assert client1 is client2
    assert isinstance(client1, GeminiClient)
    # __init__ should only be called once for the first creation
    assert GeminiClient.__init__.call_count == 1

def test_factory_creates_multiple_different_clients(mocker):
    """Tests that the factory can create different clients."""
    mocker.patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key', 'OLLAMA_MODEL': 'test-ollama'})
    mocker.patch('src.llm.clients.GeminiClient.__init__', return_value=None)
    mocker.patch('src.llm.clients.OllamaClient.__init__', return_value=None)

    gemini_client = LLMClientFactory.create_client("gemini")
    ollama_client = LLMClientFactory.create_client("ollama")

    assert gemini_client is not ollama_client
    assert isinstance(gemini_client, GeminiClient)
    assert isinstance(ollama_client, OllamaClient)

@patch.dict('os.environ', {'LMSTUDIO_BASE_URL': 'http://fake-lmstudio-url:1234/v1'})
def test_factory_creates_lmstudio_client(mocker):
    """Tests that the factory can create an LMStudioClient."""
    mocker.patch('src.llm.clients.LMStudioClient.__init__', return_value=None)
    
    client = LLMClientFactory.create_client("lmstudio")

    assert isinstance(client, LMStudioClient)
    LMStudioClient.__init__.assert_called_once()

def test_factory_raises_error_for_missing_lmstudio_url(mocker):
    """Tests that the factory raises a ValueError if LMSTUDIO_BASE_URL is not set."""
    mocker.patch.dict('os.environ', clear=True)
    with pytest.raises(ValueError, match="LMSTUDIO_BASE_URL environment variable not set"):
        LLMClientFactory.create_client("lmstudio")