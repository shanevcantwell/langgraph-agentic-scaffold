import pytest
from unittest.mock import patch
from src.llm.factory import AdapterFactory
from src.llm.adapters import GeminiAdapter, LMStudioAdapter

@patch('src.llm.factory.ConfigLoader')
def test_factory_creates_gemini_adapter(mock_config_loader):
    """Tests that the factory correctly creates a GeminiAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "gemini_config": {"type": "gemini", "api_identifier": "gemini-test"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "gemini_config"}
        }
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    # Act
    factory = AdapterFactory()
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    assert isinstance(adapter, GeminiAdapter)

@patch('src.llm.factory.ConfigLoader')
def test_factory_creates_lmstudio_adapter(mock_config_loader):
    """Tests that the factory correctly creates an LMStudioAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "lmstudio_config": {"type": "lmstudio", "api_identifier": "lmstudio-test"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "lmstudio_config"}
        }
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    # Act
    factory = AdapterFactory()
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    assert isinstance(adapter, LMStudioAdapter)

@patch('src.llm.factory.ConfigLoader')
def test_factory_returns_none_for_procedural_specialist(mock_config_loader):
    """Tests that the factory returns None for non-LLM specialists."""
    # Arrange
    mock_config = {
        "specialists": {
            "procedural_specialist": {"type": "procedural"}
        }
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    # Act
    factory = AdapterFactory()
    adapter = factory.create_adapter("procedural_specialist", "system prompt")

    # Assert
    assert adapter is None

@patch('src.llm.factory.ConfigLoader')
def test_factory_raises_error_for_unknown_provider(mock_config_loader):
    """Tests that the factory raises a ValueError for an unregistered provider type."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "unknown_config": {"type": "unknown_provider", "api_identifier": "test"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "unknown_config"}
        }
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    # Act & Assert
    factory = AdapterFactory()
    with pytest.raises(ValueError, match="Unknown base provider type 'unknown_provider'"):
        factory.create_adapter("test_specialist", "system prompt")