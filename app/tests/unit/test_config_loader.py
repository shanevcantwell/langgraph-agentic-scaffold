# app/tests/unit/test_config_loader.py
import pytest
from unittest.mock import patch, mock_open, call
from app.src.utils.config_loader import ConfigLoader
from app.src.utils.errors import ConfigError

BASE_CONFIG_YAML = """
workflow:
  entry_point: 'router_specialist'

specialists:
  router_specialist:
    type: 'llm'
    prompt_file: 'router.md'
    description: 'Routes things'
  file_specialist:
    type: 'procedural'
    description: 'File ops'
"""

USER_SETTINGS_YAML_FOR_BASIC_TEST = """
llm_providers:
  gemini_flash:
    type: 'gemini'
    api_identifier: 'gemini-2.5-flash-test'
specialist_model_bindings:
  router_specialist: 'gemini_flash'
"""


USER_SETTINGS_YAML = """
default_llm_config: 'gemini_flash'

specialist_model_bindings:
  router_specialist: 'user_provider'

llm_providers:
  gemini_flash:
    type: 'gemini'
    api_identifier: 'gemini-1.5-flash'
  user_provider:
    type: 'lmstudio'
    api_identifier: 'user-model-id'
"""

@pytest.fixture(autouse=True)
def clear_singleton():
    """Fixture to automatically reset the ConfigLoader singleton before each test."""
    ConfigLoader._instance = None
    ConfigLoader._merged_config = None
    yield

def test_singleton_pattern(mocker):
    """Tests that ConfigLoader is a singleton."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=BASE_CONFIG_YAML)(). __enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_YAML_FOR_BASIC_TEST)(). __enter__()
        raise FileNotFoundError(file)
    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    
    instance1 = ConfigLoader()
    instance2 = ConfigLoader()
    assert instance1 is instance2

def test_load_and_get_config(mocker):
    """Tests loading a basic config and retrieving it."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=BASE_CONFIG_YAML)(). __enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_YAML_FOR_BASIC_TEST)(). __enter__()
        raise FileNotFoundError(file)
    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)

    loader = ConfigLoader()
    config = loader.get_config()
    assert "specialists" in config

@patch("builtins.open", side_effect=FileNotFoundError)
@patch("os.path.exists", return_value=False)
def test_missing_config_file(mock_exists, mock_open):
    """Tests that a ConfigError is raised if config.yaml is missing."""
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
workflow:
  entry_point: 'router_specialist'
specialists:
  router_specialist:
    type: 'llm'
    prompt_file: 'router.md'
    description: 'Routes things'
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
        assert config.get("specialists", {}).get("router_specialist", {}).get("llm_config") == 'user_provider'
        # Assert provider definitions from user_settings.yaml
        assert config.get("llm_providers", {}).get("gemini_flash", {}).get("api_identifier") == 'gemini-1.5-flash'
        assert config.get("llm_providers", {}).get("user_provider", {}).get("api_identifier") == 'user-model-id'

@patch("builtins.open", new_callable=mock_open, read_data="")
@patch("os.path.exists", return_value=True)
def test_empty_config_file(mock_exists, mock_file):
    """Tests that an empty config file raises a ConfigError."""
    with pytest.raises(ConfigError, match="Configuration file is empty"):
        ConfigLoader()