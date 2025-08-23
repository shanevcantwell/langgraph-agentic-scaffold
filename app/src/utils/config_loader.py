# app/src/utils/config_loader.py
import yaml
import os
import logging
from pydantic import ValidationError

import copy
from .errors import ConfigError
from .config_schema import RootConfig, UserSettings
from .path_utils import PROJECT_ROOT

logger = logging.getLogger(__name__)
BLUEPRINT_CONFIG_FILE = PROJECT_ROOT / "config.yaml"
USER_SETTINGS_FILE = PROJECT_ROOT / "user_settings.yaml"

class ConfigLoader:
    _merged_config: dict = None
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance._load_and_merge_configs()
        return cls._instance

    def _load_and_merge_configs(self):
        """Loads, validates, and merges the blueprint and user settings."""
        if ConfigLoader._merged_config is not None:
            return

        blueprint_config = self._load_yaml_with_schema(BLUEPRINT_CONFIG_FILE, RootConfig)
        user_settings = self._load_yaml_with_schema(USER_SETTINGS_FILE, UserSettings, is_optional=True)

        # If user settings don't exist, create a default empty one
        if user_settings is None:
            user_settings = UserSettings().model_dump()
            logger.info(f"User settings file not found at {USER_SETTINGS_FILE}. Proceeding with defaults.")

        # Merge the configurations
        merged_config = self._merge_configs(blueprint_config, user_settings) if blueprint_config else {}
        ConfigLoader._merged_config = merged_config
        logger.info("Configuration loaded, validated, and merged successfully.")

    def _load_yaml_with_schema(self, file_path, schema_model, is_optional=False):
        """Loads a single YAML file and validates it against a Pydantic schema."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                logger.debug(f"Loading configuration file: {file_path}")
                raw_config = yaml.safe_load(f)

            if not raw_config:
                if is_optional:
                    logger.debug(f"Optional configuration file is empty or not found: {file_path}")
                    return None
                raise ConfigError(f"Configuration file is empty: {file_path}")

            validated_config = schema_model(**raw_config)
            logger.debug(f"Successfully validated configuration file: {file_path}")
            return validated_config.model_dump()

        except FileNotFoundError:
            if is_optional:
                logger.debug(f"Optional configuration file not found: {file_path}")
                return None
            msg = f"Required configuration file '{file_path}' not found."
            logger.error(msg)
            raise ConfigError(msg) from None
        except yaml.YAMLError as e:
            msg = f"Error parsing YAML from '{file_path}': {e}"
            logger.error(msg)
            raise ConfigError(msg) from e
        except ValidationError as e:
            msg = f"Configuration validation failed for '{file_path}':\n{e}"
            logger.error(msg)
            raise ConfigError(msg) from e

    def _merge_configs(self, blueprint: dict, user_settings: dict) -> dict:
        """Injects user choices into the blueprint to create the final config."""
        logger.debug("Starting configuration merge process.")
        merged = copy.deepcopy(blueprint)
        bindings = user_settings.get("specialist_model_bindings", {})
        default_binding = user_settings.get("default_llm_config")

        if default_binding:
            logger.debug(f"Default LLM binding set to: '{default_binding}'")
            if default_binding not in merged["llm_providers"]:
                raise ConfigError(f"The 'default_llm_config' ('{default_binding}') in {USER_SETTINGS_FILE} does not exist in 'llm_providers' in {BLUEPRINT_CONFIG_FILE}.")

        for name, spec_config in merged["specialists"].items():
            if spec_config.get("type") == "llm":
                # Determine the binding: specific binding > default binding > None
                binding = bindings.get(name) or default_binding
                if not binding:
                    raise ConfigError(
                        f"LLM specialist '{name}' has no model assigned. "
                        f"Assign it in 'specialist_model_bindings' or set a 'default_llm_config' in {USER_SETTINGS_FILE}."
                    )
                if binding not in merged["llm_providers"]:
                    raise ConfigError(
                        f"Model binding '{binding}' for specialist '{name}' in {USER_SETTINGS_FILE} "
                        f"does not exist in 'llm_providers' in {BLUEPRINT_CONFIG_FILE}."
                    )
                # Inject the final llm_config into the specialist's configuration
                spec_config["llm_config"] = binding
                logger.debug(f"Bound specialist '{name}' to LLM config: '{binding}'")

        logger.debug("Configuration merge process completed.")
        return merged

    def get_config(self) -> dict:
        """Returns the final, merged configuration."""
        return ConfigLoader._merged_config
