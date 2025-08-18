import os
import yaml
from typing import Dict, Any

class ConfigLoader:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            config_path = os.path.join(os.path.dirname(__file__), '../../../config.yaml')
            with open(config_path, 'r') as f:
                cls._config = yaml.safe_load(f)
        return cls._instance

    def get_specialist_config(self, specialist_name: str) -> Dict[str, Any]:
        return self._config['specialists'][specialist_name]

    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        return self._config['models'][model_name]

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        return self._config['providers'][provider_name]

    def get_config(self) -> Dict[str, Any]:
        return self._config
