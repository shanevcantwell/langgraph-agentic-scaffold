import pytest
from src.llm.factory import AdapterFactory
from src.llm.adapters import GeminiAdapter, LMStudioAdapter

def test_factory_creates_gemini_adapter():
    """Tests that the factory correctly creates a GeminiAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "gemini_config": {"type": "gemini", "api_identifier": "gemini-test", "api_key": "fake-key"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "gemini_config"}
        }
    }
    
    # Act
    factory = AdapterFactory(mock_config)
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    assert isinstance(adapter, GeminiAdapter)

def test_factory_creates_lmstudio_adapter():
    """Tests that the factory correctly creates an LMStudioAdapter."""
    # Arrange
    mock_config = {
        "llm_providers": {
            "lmstudio_config": {"type": "lmstudio", "api_identifier": "lmstudio-test", "base_url": "http://localhost:1234/v1"}
        },
        "specialists": {
            "test_specialist": {"type": "llm", "llm_config": "lmstudio_config"}
        }
    }
    
    # Act
    factory = AdapterFactory(mock_config)
    adapter = factory.create_adapter("test_specialist", "system prompt")

    # Assert
    assert isinstance(adapter, LMStudioAdapter)

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
            "test_specialist": {"type": "llm", "llm_config": "unknown_config"}
        }
    }
    
    # Act & Assert
    factory = AdapterFactory(mock_config)
    with pytest.raises(ValueError, match="Unknown base provider type 'unknown_provider'"):
        factory.create_adapter("test_specialist", "system prompt")