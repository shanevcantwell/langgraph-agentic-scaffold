# app/tests/unit/test_config_loader.py
import pytest
from unittest.mock import patch, mock_open, call
from app.src.utils.config_loader import ConfigLoader
from app.src.utils.errors import ConfigError

BASE_CONFIG_YAML = """
llm_providers:
  gemini_flash:
    type: "gemini"

workflow:
  entry_point: "router_specialist"
  recursion_limit: 25

specialists:
  router_specialist:
    type: llm
    prompt_file: "router.md"
    description: "Routes things"
  file_specialist:
    type: procedural
    description: "File ops"
"""

USER_SETTINGS_YAML = """
default_llm_config: "gemini_flash"

specialist_model_bindings:
  router_specialist: user_provider

provider_models:
  gemini_flash:
    api_identifier: "gemini-1.5-flash"
  user_provider:
    api_identifier: "user-model-id"
"""

@pytest.fixture(autouse=True)
def clear_singleton():
    """Fixture to automatically reset the ConfigLoader singleton before each test."""
    ConfigLoader._instance = None
    ConfigLoader._merged_config = None
    yield

def test_singleton_pattern():
    """Tests that ConfigLoader is a singleton."""
    user_settings_for_singleton = """
default_llm_config: "gemini_flash"
provider_models:
  gemini_flash:
    api_identifier: "gemini-1.5-flash"
"""
    # Test the singleton pattern under success conditions
    with patch("builtins.open", mock_open(read_data=user_settings_for_singleton)) as m_open, \
         patch("os.path.exists", return_value=True):
        m_open.side_effect = [mock_open(read_data=BASE_CONFIG_YAML).return_value, mock_open(read_data=user_settings_for_singleton).return_value]
        instance1 = ConfigLoader() # First call
        instance2 = ConfigLoader() # Second call should be cached
        assert instance1 is instance2 # Verify singleton

@patch("builtins.open", new_callable=mock_open, read_data=BASE_CONFIG_YAML)
@patch("os.path.exists", return_value=True)
def test_load_and_get_config(mock_exists, mock_file):
    """Tests loading a basic config with a default binding."""
    user_settings_with_default = """
default_llm_config: "gemini_flash"
provider_models:
  gemini_flash:
    api_identifier: "gemini-1.5-flash"
"""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=BASE_CONFIG_YAML)(). __enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=user_settings_with_default)(). __enter__()
        raise FileNotFoundError(file)

    with patch("builtins.open", side_effect=mock_open_side_effect):
        config = ConfigLoader().get_config()
        assert config["specialists"]["router_specialist"]["llm_config"] == "gemini_flash"

def test_missing_config_file():
    """Tests that a FileNotFoundError is raised if config.yaml is missing."""
    # To correctly test this, we need to mock both `os.path.exists` and `open`.
    # 1. `os.path.exists` should return False for config.yaml and True for user_settings.yaml.
    # 2. `open` should raise FileNotFoundError when trying to open config.yaml.
    def mock_exists_side_effect(path):
        return "user_settings.yaml" in str(path)

    def mock_open_side_effect(file, *args, **kwargs):
        if "config.yaml" in str(file):
            raise FileNotFoundError
        # For user_settings.yaml, return a mock file object with empty content.
        return mock_open(read_data="")(). __enter__()

    with patch("os.path.exists", side_effect=mock_exists_side_effect), \
         patch("builtins.open", side_effect=mock_open_side_effect):
        with pytest.raises(ConfigError, match="Required configuration file .*config.yaml.* not found."):
            ConfigLoader()

def test_malformed_yaml():
    """Tests that a YAMLError is raised for invalid YAML."""
    malformed_yaml = "key: value:\n  - invalid"
    with patch("builtins.open", mock_open(read_data=malformed_yaml)), \
         patch("os.path.exists", return_value=True):
        with pytest.raises(ConfigError, match="Error parsing YAML"):
            ConfigLoader()

def test_merge_user_settings():
    """Tests that user_settings.yaml correctly merges with and overrides config.yaml."""
    # This base config is more representative of the real one.
    base_config_for_merge = """
llm_providers:
  gemini_flash:
    type: gemini
  user_provider:
    type: lmstudio
workflow:
  entry_point: "router_specialist"
specialists:
  router_specialist:
    type: llm
    prompt_file: "router.md"
    description: "Routes things"
"""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=base_config_for_merge)(). __enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_YAML)(). __enter__()
        raise FileNotFoundError(file)

    # os.path.exists needs to be mocked to find both files
    def mock_exists_side_effect(path):
        return 'config.yaml' in str(path) or 'user_settings.yaml' in str(path)

    with patch("builtins.open", side_effect=mock_open_side_effect), \
         patch("os.path.exists", side_effect=mock_exists_side_effect):
        
        config = ConfigLoader().get_config()

        # Assert override from specialist_model_bindings
        assert config["specialists"]["router_specialist"]["llm_config"] == "user_provider"
        # Assert model identifier injection from provider_models
        assert config["llm_providers"]["gemini_flash"]["api_identifier"] == "gemini-1.5-flash"
        assert config["llm_providers"]["user_provider"]["api_identifier"] == "user-model-id"

@patch("builtins.open", new_callable=mock_open, read_data="")
@patch("os.path.exists", return_value=True)
def test_empty_config_file(mock_exists, mock_file):
    """Tests that an empty config file raises a ConfigError."""
    with pytest.raises(ConfigError, match="Configuration file is empty"):
        ConfigLoader()
