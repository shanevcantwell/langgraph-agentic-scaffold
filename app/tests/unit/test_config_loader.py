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
    """Fixture to automatically reset the ConfigLoader singleton before each test and restore after."""
    # Save original state
    original_instance = ConfigLoader._instance
    original_config = ConfigLoader._merged_config
    # Clear for test isolation
    ConfigLoader._instance = None
    ConfigLoader._merged_config = None
    yield
    # Restore original state to avoid polluting subsequent tests
    ConfigLoader._instance = original_instance
    ConfigLoader._merged_config = original_config

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


# ===================================================================
# LMSTUDIO_SERVERS Distributed Inference Tests
# ===================================================================

CONFIG_WITH_LMSTUDIO = """
workflow:
  entry_point: 'router_specialist'

specialists:
  router_specialist:
    type: 'llm'
    prompt_file: 'router.md'
    description: 'Routes things'
"""

USER_SETTINGS_WITH_SERVER = """
llm_providers:
  lmstudio_router:
    type: 'lmstudio'
    server: 'rtx3090'
    api_identifier: 'gpt-oss-20b'
  lmstudio_specialist:
    type: 'lmstudio'
    server: 'rtx8000'
    api_identifier: 'qwen3-30b'
  lmstudio_local:
    type: 'lmstudio'
    api_identifier: 'gemma-12b'
specialist_model_bindings:
  router_specialist: 'lmstudio_router'
"""


def test_lmstudio_servers_parsing(mocker):
    """Tests that LOCAL_INFERENCE_SERVERS env var is parsed correctly."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_LMSTUDIO)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_WITH_SERVER)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {
        "LOCAL_INFERENCE_SERVERS": "rtx3090=http://192.168.1.100:1234/v1,rtx8000=http://192.168.1.101:1234/v1",
        "LOCAL_INFERENCE_BASE_URL": "http://localhost:1234/v1"
    })

    loader = ConfigLoader()
    config = loader.get_config()

    # Check that server references resolve correctly
    assert config["llm_providers"]["lmstudio_router"]["base_url"] == "http://192.168.1.100:1234/v1"
    assert config["llm_providers"]["lmstudio_specialist"]["base_url"] == "http://192.168.1.101:1234/v1"
    # Provider without server should fall back to LOCAL_INFERENCE_BASE_URL
    assert config["llm_providers"]["lmstudio_local"]["base_url"] == "http://localhost:1234/v1"


def test_lmstudio_servers_missing_server_name(mocker):
    """Tests warning when server name not found in LMSTUDIO_SERVERS."""
    user_settings_bad_server = """
llm_providers:
  lmstudio_router:
    type: 'lmstudio'
    server: 'nonexistent'
    api_identifier: 'gpt-oss-20b'
specialist_model_bindings:
  router_specialist: 'lmstudio_router'
"""

    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_LMSTUDIO)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=user_settings_bad_server)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {
        "LOCAL_INFERENCE_SERVERS": "rtx3090=http://192.168.1.100:1234/v1",
        "LOCAL_INFERENCE_BASE_URL": "http://localhost:1234/v1"
    })

    loader = ConfigLoader()
    config = loader.get_config()

    # Server not found should result in None base_url
    assert config["llm_providers"]["lmstudio_router"]["base_url"] is None


def test_lmstudio_servers_empty(mocker):
    """Tests fallback when LOCAL_INFERENCE_SERVERS is empty — server reference should resolve to None."""
    user_settings_with_server = """
llm_providers:
  lmstudio_router:
    type: 'lmstudio'
    server: 'rtx3090'
    api_identifier: 'gpt-oss-20b'
specialist_model_bindings:
  router_specialist: 'lmstudio_router'
"""

    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_LMSTUDIO)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=user_settings_with_server)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {
        "LOCAL_INFERENCE_SERVERS": "",  # Empty
        "LOCAL_INFERENCE_BASE_URL": "http://localhost:1234/v1"
    })

    loader = ConfigLoader()
    config = loader.get_config()

    # With empty LOCAL_INFERENCE_SERVERS, server reference should result in None
    assert config["llm_providers"]["lmstudio_router"]["base_url"] is None


def test_lmstudio_servers_with_spaces(mocker):
    """Tests that LOCAL_INFERENCE_SERVERS handles whitespace gracefully."""
    def mock_open_side_effect(file, mode='r', encoding=None):
        if 'config.yaml' in str(file):
            return mock_open(read_data=CONFIG_WITH_LMSTUDIO)().__enter__()
        if 'user_settings.yaml' in str(file):
            return mock_open(read_data=USER_SETTINGS_WITH_SERVER)().__enter__()
        raise FileNotFoundError(file)

    mocker.patch("builtins.open", side_effect=mock_open_side_effect)
    mocker.patch("os.path.exists", return_value=True)
    mocker.patch.dict("os.environ", {
        # Extra whitespace around entries
        "LOCAL_INFERENCE_SERVERS": " rtx3090 = http://192.168.1.100:1234/v1 , rtx8000 = http://192.168.1.101:1234/v1 ",
        "LOCAL_INFERENCE_BASE_URL": "http://localhost:1234/v1"
    })

    loader = ConfigLoader()
    config = loader.get_config()

    # Should handle whitespace correctly
    assert config["llm_providers"]["lmstudio_router"]["base_url"] == "http://192.168.1.100:1234/v1"
    assert config["llm_providers"]["lmstudio_specialist"]["base_url"] == "http://192.168.1.101:1234/v1"