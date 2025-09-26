
import pytest
from unittest.mock import patch, MagicMock
from app.src.llm.factory import AdapterFactory
from app.src.llm.gemini_adapter import GeminiAdapter
from app.src.llm.lmstudio_adapter import LMStudioAdapter

def test_factory_creates_gemini_adapter():
    """Tests that the factory correctly creates a GeminiAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "gemini_config": {"type": "gemini", "api_identifier": "gemini-test", "api_key": "fake-key"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "gemini_config", "prompt_file": "fake.md"}
        }
    }
    
    # Act
    factory = AdapterFactory(mock_config)
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    assert isinstance(adapter, GeminiAdapter)

@patch('app.src.llm.lmstudio_adapter.LMStudioAdapter.from_config')
def test_factory_creates_lmstudio_adapter(mock_from_config):
    """Tests that the factory correctly creates an LMStudioAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "lmstudio_config": {"type": "lmstudio", "api_identifier": "lmstudio-test", "base_url": "http://localhost:1234/v1"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "lmstudio_config", "prompt_file": "fake.md"}
        }
    }
    
    # Act
    factory = AdapterFactory(mock_config)
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    mock_from_config.assert_called_once()

def test_factory_returns_none_for_procedural_specialist():
    """Tests that the factory returns None for non-LLM specialists."""
    # Arrange
    mock_config = {
        "specialists": {
            "procedural_specialist": {"type": "procedural"}
        }
    }
    
    # Act
    factory = AdapterFactory(mock_config)
    adapter = factory.create_adapter("procedural_specialist", "system prompt")

    # Assert
    assert adapter is None

def test_factory_raises_error_for_unknown_provider():
    """Tests that the factory raises a ValueError for an unregistered provider type."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "unknown_config": {"type": "unknown_provider", "api_identifier": "test"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "unknown_config", "prompt_file": "fake.md"}
        }
    }
    
    # Act & Assert
    factory = AdapterFactory(mock_config)
    with pytest.raises(ValueError, match="Unknown base provider type 'unknown_provider'"):
        factory.create_adapter("test_specialist", "system prompt")

def test_factory_raises_error_for_missing_llm_config():
    """Tests that an error is raised if an LLM specialist is missing the 'llm_config' key."""
    # Arrange
    mock_config = {
        "specialists": {
            "bad_specialist": {"type": "llm"} # Missing 'llm_config'
        }
    }
    factory = AdapterFactory(mock_config)

    # Act & Assert
    with pytest.raises(ValueError, match="LLM specialist 'bad_specialist' is missing 'llm_config' key."):
        factory.create_adapter("bad_specialist", "system prompt")

def test_factory_raises_error_for_unresolvable_provider():
    """Tests that an error is raised if 'llm_config' points to a non-existent provider."""
    # Arrange
    mock_config = {
        "llm_providers": {"real_provider": {"type": "gemini"}}, # Empty providers
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "non_existent_provider", "prompt_file": "fake.md"}
        }
    }
    factory = AdapterFactory(mock_config)

    # Act & Assert
    with pytest.raises(ValueError, match="Provider 'non_existent_provider' for specialist 'test_specialist' not found in 'llm_providers'."):
        factory.create_adapter("test_specialist", "system prompt")