# app/tests/unit/test_llm_factory.py

import pytest
from unittest.mock import MagicMock, patch
from app.src.llm.factory import AdapterFactory
from app.src.llm.adapters import GeminiAdapter, LMStudioAdapter

@pytest.fixture
def mock_full_config():
    """Provides a mock full_config dictionary for testing the factory."""
    return {
        "specialists": {
            "llm_specialist": {
                "type": "llm",
                "llm_config": "gemini_provider"
            },
            "hybrid_specialist": {
                "type": "hybrid",
                "llm_config": "lmstudio_provider"
            },
            "procedural_specialist": {
                "type": "procedural"
                # No llm_config
            },
            "missing_binding_specialist": {
                "type": "llm"
                # Missing llm_config key
            },
            "unresolvable_binding_specialist": {
                "type": "llm",
                "llm_config": "non_existent_provider"
            },
            "unknown_provider_type_specialist": {
                "type": "llm",
                "llm_config": "unknown_provider"
            }
        },
        "llm_providers": {
            "gemini_provider": {"type": "gemini", "api_identifier": "gemini-pro"},
            "lmstudio_provider": {"type": "lmstudio", "api_identifier": "lmstudio-model"},
            "unknown_provider": {"type": "future_provider_type"},
        }
    }

@pytest.fixture
def adapter_factory(mock_full_config):
    """Provides an AdapterFactory instance initialized with mock config."""
    return AdapterFactory(mock_full_config)

@patch('app.src.llm.adapters.GeminiAdapter.from_config')
def test_factory_creates_adapter_for_llm_specialist(mock_from_config, adapter_factory):
    """Tests that an adapter is correctly created for a specialist of type 'llm'."""
    mock_from_config.return_value = MagicMock(spec=GeminiAdapter)
    adapter = adapter_factory.create_adapter("llm_specialist", "system prompt")
    assert adapter is not None
    assert isinstance(adapter, MagicMock)
    mock_from_config.assert_called_once()

@patch('app.src.llm.adapters.LMStudioAdapter.from_config')
def test_factory_creates_adapter_for_hybrid_specialist(mock_from_config, adapter_factory):
    """Tests that an adapter is correctly created for the new 'hybrid' specialist type."""
    mock_from_config.return_value = MagicMock(spec=LMStudioAdapter)
    adapter = adapter_factory.create_adapter("hybrid_specialist", "system prompt")
    assert adapter is not None
    assert isinstance(adapter, MagicMock)
    mock_from_config.assert_called_once()

def test_factory_returns_none_for_procedural_specialist(adapter_factory):
    """Tests that no adapter is created for a 'procedural' specialist."""
    adapter = adapter_factory.create_adapter("procedural_specialist", "system prompt")
    assert adapter is None

def test_factory_raises_error_for_missing_llm_config(adapter_factory):
    """Tests that a ValueError is raised if 'llm_config' is missing for an LLM specialist."""
    with pytest.raises(ValueError, match="is missing 'llm_config' key"):
        adapter_factory.create_adapter("missing_binding_specialist", "system prompt")

def test_factory_raises_error_for_unresolvable_provider(adapter_factory):
    """Tests that a ValueError is raised if the provider key in 'llm_config' doesn't exist."""
    with pytest.raises(ValueError, match="not found in 'llm_providers'"):
        adapter_factory.create_adapter("unresolvable_binding_specialist", "system prompt")

def test_factory_returns_none_for_unknown_provider_type(adapter_factory):
    """Tests that the factory returns None if the provider 'type' is not in the registry."""
    adapter = adapter_factory.create_adapter("unknown_provider_type_specialist", "system prompt")
    assert adapter is None