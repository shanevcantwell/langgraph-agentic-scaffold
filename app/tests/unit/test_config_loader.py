# Audited on Sept 23, 2025
# app/tests/unit/test_config_loader.py
import pytest
import yaml
from unittest.mock import patch, mock_open
from app.src.utils.config_loader import ConfigLoader

BASE_CONFIG_YAML = """
llm_providers:
  default_provider:
    type: gemini
    api_identifier: gemini-pro

specialists:
  router:
    llm_config: default_provider
  file_specialist:
    type: procedural
"""

USER_SETTINGS_YAML = """
specialists:
  router:
    llm_config: user_provider # Override the provider

llm_providers:
  user_provider: # Add a new provider
    type: lmstudio
    api_identifier: user-model
"""

@pytest.fixture(autouse=True)
def clear_singleton():
    """Fixture to automatically reset the ConfigLoader singleton before each test."""
    ConfigLoader._instance = None
    ConfigLoader._config = None
    yield

def test_singleton_pattern():
    """Tests that ConfigLoader is a singleton."""
    with patch("os.path.exists", return_value=False): # Prevent file loading
        instance1 = ConfigLoader()
        instance2 = ConfigLoader()
        assert instance1 is instance2

@patch("builtins.open", new_callable=mock_open, read_data=BASE_CONFIG_YAML)
@patch("os.path.exists", return_value=True)
def test_load_and_get_config(mock_exists, mock_file):
    """Tests loading a basic config and retrieving it."""
    config = ConfigLoader().get_config()
    assert "specialists" in config
    assert "llm_providers" in config
    assert config["specialists"]["router"]["llm_config"] == "default_provider"

@patch("builtins.open", new_callable=mock_open, read_data=BASE_CONFIG_YAML)
@patch("os.path.exists", return_value=True)
def test_get_specialist_config(mock_exists, mock_file):
    """Tests retrieving a specific specialist's configuration."""
    loader = ConfigLoader()
    spec_config = loader.get_specialist_config("file_specialist")
    assert spec_config["type"] == "procedural"

@patch("builtins.open", new_callable=mock_open, read_data=BASE_CONFIG_YAML)
@patch("os.path.exists", return_value=True)
def test_get_provider_config(mock_exists, mock_file):
    """Tests retrieving a specific provider's configuration."""
    loader = ConfigLoader()
    prov_config = loader.get_provider_config("default_provider")
    assert prov_config["type"] == "gemini"

def test_missing_config_file():
    """Tests that a FileNotFoundError is raised if config.yaml is missing."""
    with patch("os.path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="Configuration file 'config.yaml' not found."):
            ConfigLoader()

def test_malformed_yaml():
    """Tests that a YAMLError is raised for invalid YAML."""
    malformed_yaml = "key: value:\n  - invalid"
    with patch("builtins.open", mock_open(read_data=malformed_yaml)), \
         patch("os.path.exists", return_value=True):
        with pytest.raises(yaml.YAMLError):
            ConfigLoader()

def test_merge_user_settings():
    """Tests that user_settings.yaml correctly merges with and overrides config.yaml."""
    def mock_open_side_effect(file, mode='r'):
        if file == 'config.yaml':
            return mock_open(read_data=BASE_CONFIG_YAML)(). __enter__()
        if file == 'user_settings.yaml':
            return mock_open(read_data=USER_SETTINGS_YAML)(). __enter__()
        raise FileNotFoundError(file)

    with patch("builtins.open", side_effect=mock_open_side_effect), \
         patch("os.path.exists", return_value=True):
        
        config = ConfigLoader().get_config()

        # Assert override
        assert config["specialists"]["router"]["llm_config"] == "user_provider"
        # Assert addition
        assert "user_provider" in config["llm_providers"]
        assert config["llm_providers"]["user_provider"]["type"] == "lmstudio"
        # Assert original exists
        assert "default_provider" in config["llm_providers"]

@patch("builtins.open", new_callable=mock_open, read_data="")
@patch("os.path.exists", return_value=True)
def test_empty_config_file(mock_exists, mock_file):
    """Tests that an empty config file loads as an empty dictionary."""
    config = ConfigLoader().get_config()
    assert config == {}
