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
  hybrid_specialist:
    type: 'hybrid'
    description: 'Hybrid ops'
"""

USER_SETTINGS_YAML_FOR_BASIC_TEST = """
llm_providers:
  gemini_flash:
    type: 'gemini'
    api_identifier: 'gemini-2.5-flash-test'
specialist_model_bindings:
  router_specialist: 'gemini_flash'
  hybrid_specialist: 'gemini_flash'
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
    assert "hybrid_specialist" in config["specialists"]

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
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=BASE_CONFIG_YAML)(). __enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_YAML)(). __enter__()
        raise FileNotFoundError(file)

    def mock_exists_side_effect(path):
        return 'config.yaml' in str(path) or 'user_settings.yaml' in str(path)

    with patch("builtins.open", side_effect=mock_open_side_effect), \
         patch("os.path.exists", side_effect=mock_exists_side_effect):
        
        config = ConfigLoader().get_config()

        assert config.get("specialists", {}).get("router_specialist", {}).get("llm_config") == 'user_provider'
        assert config.get("llm_providers", {}).get("gemini_flash", {}).get("api_identifier") == 'gemini-1.5-flash'
        assert config.get("llm_providers", {}).get("user_provider", {}).get("api_identifier") == 'user-model-id'
        # Hybrid specialist should get the default binding
        assert config.get("specialists", {}).get("hybrid_specialist", {}).get("llm_config") == 'gemini_flash'

@patch("builtins.open", new_callable=mock_open, read_data="")
@patch("os.path.exists", return_value=True)
def test_empty_config_file(mock_exists, mock_file):
    """Tests that an empty config file raises a ConfigError."""
    with pytest.raises(ConfigError, match="Configuration file is empty"):
        ConfigLoader()


# ===================================================================
# Environment Variable Substitution Tests
# ===================================================================

CONFIG_WITH_ENV_VARS = """
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
    root_dir: '${WORKSPACE_PATH:-workspace}'
"""

USER_SETTINGS_WITH_ENV_VARS = """
llm_providers:
  gemini_flash:
    type: 'gemini'
    api_identifier: 'gemini-2.5-flash-test'
specialist_model_bindings:
  router_specialist: 'gemini_flash'
"""


def test_env_var_substitution_with_default(mocker):
    """Tests that env vars are substituted with default value when not set."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_ENV_VARS)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_WITH_ENV_VARS)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {}, clear=True)  # Clear env vars

    loader = ConfigLoader()
    config = loader.get_config()

    # Should use default value "workspace" since WORKSPACE_PATH is not set
    assert config["specialists"]["file_specialist"]["root_dir"] == "workspace"


def test_env_var_substitution_with_env_value(mocker):
    """Tests that env vars are substituted with actual env value when set."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_ENV_VARS)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_WITH_ENV_VARS)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {"WORKSPACE_PATH": "custom_workspace"})

    loader = ConfigLoader()
    config = loader.get_config()

    # Should use env value "custom_workspace"
    assert config["specialists"]["file_specialist"]["root_dir"] == "custom_workspace"


def test_env_var_substitution_required_missing():
    """Tests that missing required env var (no default) raises ConfigError."""
    config_with_required_var = """
workflow:
  entry_point: 'router_specialist'

specialists:
  router_specialist:
    type: 'llm'
    prompt_file: 'router.md'
    description: 'Routes things'
    required_path: '${REQUIRED_VAR}'
"""

    user_settings_minimal = """
llm_providers:
  gemini_flash:
    type: 'gemini'
    api_identifier: 'gemini-2.5-flash-test'
specialist_model_bindings:
  router_specialist: 'gemini_flash'
"""

    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=config_with_required_var)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=user_settings_minimal)().__enter__()
        raise FileNotFoundError(file)

    with patch("builtins.open", side_effect=mock_open_side_effect), \
         patch("os.path.exists", return_value=True), \
         patch.dict("os.environ", {}, clear=True):

        with pytest.raises(ConfigError, match="Required environment variable 'REQUIRED_VAR' is not set"):
            ConfigLoader()