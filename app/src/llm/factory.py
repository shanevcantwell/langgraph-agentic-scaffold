# app/src/llm/factory.py
import logging
from typing import Dict, Any
from .adapter import BaseAdapter
from .adapters import GeminiAdapter, LMStudioAdapter # Import all possible adapters

logger = logging.getLogger(__name__)

# --- Adapter Registry ---
# This mapping provides a robust, explicit link between the provider name
# in config.yaml and the corresponding adapter class. It avoids brittle
# string manipulation and makes the factory easily extensible.
ADAPTER_REGISTRY = {
    "gemini": GeminiAdapter,
    "lmstudio": LMStudioAdapter,
    # "ollama": OllamaAdapter, # Example for future extension
}

class AdapterFactory:
    def __init__(self, full_config: Dict[str, Any]):
        self.full_config = full_config

    def create_adapter(self, binding_key: str, system_prompt: str) -> BaseAdapter | None:
        """
        Creates an LLM adapter based on a provider binding key from the configuration.
        """
        if not binding_key:
            raise ValueError("Cannot create adapter: 'binding_key' was not provided.")

        # Get the full provider configuration block from the top-level `llm_providers`
        provider_config = self.full_config.get("llm_providers", {}).get(binding_key)
        if not provider_config:
            # This should also be unreachable if ConfigLoader is correct.
            raise ValueError(f"Provider configuration '{binding_key}' not found in 'llm_providers'.")
        
        # Add the binding key to the config for better error messages within the adapter.
        provider_config['binding_key'] = binding_key

        # This is the actual provider type, e.g., "gemini" or "lmstudio"
        base_provider_type = provider_config.get('type')

        # Look up the adapter class from the registry.
        AdapterClass = ADAPTER_REGISTRY.get(base_provider_type)
        if not AdapterClass:
            raise ValueError(f"Unknown base provider type '{base_provider_type}' specified in '{binding_key}'. Supported types are: {list(ADAPTER_REGISTRY.keys())}")

        # Use the adapter's own factory method to create the instance.
        return AdapterClass.from_config(provider_config, system_prompt)