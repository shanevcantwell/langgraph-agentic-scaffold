# app/tests/unit/test_llm_factory.py

import pytest
from unittest.mock import MagicMock, patch
from app.src.llm.factory import AdapterFactory
from app.src.llm.adapters import GeminiAdapter, LocalInferenceAdapter

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
            "lmstudio_provider": {"type": "local", "api_identifier": "local-model", "base_url": "http://localhost:1234/v1"},
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

@patch('app.src.llm.local_inference_adapter.LocalInferenceAdapter.from_config')
def test_factory_creates_adapter_for_hybrid_specialist(mock_from_config, adapter_factory):
    """Tests that an adapter is correctly created for the new 'hybrid' specialist type."""
    mock_from_config.return_value = MagicMock(spec=LocalInferenceAdapter)
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

# ==============================================================================
# Provider Dependency Validation Tests
# ==============================================================================

@pytest.fixture
def config_with_gemini_webui():
    """Config with gemini_webui provider bound to a specialist."""
    return {
        "specialists": {
            "distillation_specialist": {
                "type": "llm",
                "llm_config": "gemini_webui_provider"
            },
            "normal_specialist": {
                "type": "llm",
                "llm_config": "gemini_provider"
            }
        },
        "llm_providers": {
            "gemini_webui_provider": {"type": "gemini_webui", "session_cookies": "./cookies.json"},
            "gemini_provider": {"type": "gemini", "api_identifier": "gemini-pro"},
        }
    }

@patch('app.src.llm.factory._check_playwright_available')
def test_validate_dependencies_detects_missing_playwright(mock_check, config_with_gemini_webui):
    """Tests that validation detects missing Playwright for gemini_webui provider."""
    mock_check.return_value = False  # Playwright not available

    factory = AdapterFactory(config_with_gemini_webui)
    missing_deps = factory.validate_provider_dependencies()

    assert len(missing_deps) == 1
    provider_key, provider_type, error_msg = missing_deps[0]
    assert provider_key == "gemini_webui_provider"
    assert provider_type == "gemini_webui"
    assert "Playwright" in error_msg
    assert "pip install playwright" in error_msg

@patch('app.src.llm.factory._check_playwright_available')
def test_validate_dependencies_passes_when_playwright_available(mock_check, config_with_gemini_webui):
    """Tests that validation passes when Playwright is available."""
    mock_check.return_value = True  # Playwright available

    factory = AdapterFactory(config_with_gemini_webui)
    missing_deps = factory.validate_provider_dependencies()

    assert len(missing_deps) == 0

def test_validate_dependencies_ignores_unbound_providers():
    """Tests that validation only checks providers that are actually bound to specialists."""
    config = {
        "specialists": {
            "normal_specialist": {
                "type": "llm",
                "llm_config": "gemini_provider"
            }
        },
        "llm_providers": {
            "gemini_provider": {"type": "gemini", "api_identifier": "gemini-pro"},
            "gemini_webui_provider": {"type": "gemini_webui"},  # Defined but not bound
        }
    }

    factory = AdapterFactory(config)
    missing_deps = factory.validate_provider_dependencies()

    # Should be empty since gemini_webui is not bound to any specialist
    assert len(missing_deps) == 0


# ==============================================================================
# ping_provider Tests (BUG-STARTUP-001)
# ==============================================================================

from app.src.llm.factory import ping_provider


def test_ping_provider_unknown_type():
    """Tests that ping_provider handles unknown provider types gracefully."""
    provider_config = {
        "type": "unknown_future_type",
        "api_identifier": "some-model"
    }

    result = ping_provider("test_provider", provider_config)

    assert result["success"] is False
    assert result["provider"] == "test_provider"
    assert result["type"] == "unknown_future_type"
    assert "Unknown provider type" in result["error"]


@patch('app.src.llm.local_inference_adapter.LocalInferenceAdapter.from_config')
def test_ping_provider_success(mock_from_config):
    """Tests successful ping returns correct result structure."""
    mock_adapter = MagicMock()
    mock_adapter.invoke.return_value = {"text_response": "pong"}
    mock_from_config.return_value = mock_adapter

    provider_config = {
        "type": "local",
        "api_identifier": "test-model",
        "base_url": "http://localhost:1234"
    }

    result = ping_provider("test_local", provider_config)

    assert result["success"] is True
    assert result["provider"] == "test_local"
    assert result["type"] == "local"
    assert result["response"] == "pong"
    assert result["latency_ms"] is not None
    assert result["error"] is None


@patch('app.src.llm.local_inference_adapter.LocalInferenceAdapter.from_config')
def test_ping_provider_connection_error(mock_from_config):
    """Tests that ping_provider handles connection errors gracefully."""
    mock_from_config.side_effect = Exception("Connection refused")

    provider_config = {
        "type": "local",
        "api_identifier": "test-model",
        "base_url": "http://localhost:9999"
    }

    result = ping_provider("failing_provider", provider_config)

    assert result["success"] is False
    assert result["provider"] == "failing_provider"
    assert "Connection refused" in result["error"]
    assert result["latency_ms"] is None


@patch('app.src.llm.local_inference_adapter.LocalInferenceAdapter.from_config')
def test_ping_provider_invoke_error(mock_from_config):
    """Tests that ping_provider handles invocation errors gracefully."""
    mock_adapter = MagicMock()
    mock_adapter.invoke.side_effect = Exception("Model timeout")
    mock_from_config.return_value = mock_adapter

    provider_config = {
        "type": "local",
        "api_identifier": "test-model",
        "base_url": "http://localhost:1234"
    }

    result = ping_provider("timeout_provider", provider_config)

    assert result["success"] is False
    assert "Model timeout" in result["error"]