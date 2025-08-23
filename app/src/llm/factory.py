# app/src/llm/factory.py
import os
import logging
from ..utils.config_loader import ConfigLoader
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
    def create_adapter(self, specialist_name: str, system_prompt: str) -> BaseAdapter | None:
        full_config = ConfigLoader().get_config()
        spec_config = full_config.get("specialists", {}).get(specialist_name, {})

        # The new config structure makes this check explicit and simple.
        if spec_config.get("type") != "llm":
            logger.debug(f"Specialist '{specialist_name}' is not of type 'llm'. No adapter will be created.")
            return None

        # The ConfigLoader guarantees this key exists for 'llm' types.
        provider_config_key = spec_config.get("llm_config")
        if not provider_config_key:
             # This should be unreachable if ConfigLoader is correct, but serves as a safeguard.
            raise ValueError(f"LLM specialist '{specialist_name}' is missing 'llm_config' key in merged config.")

        # Get the full provider configuration block from the top-level `llm_providers`
        provider_config = full_config.get("llm_providers", {}).get(provider_config_key)
        if not provider_config:
            raise ValueError(f"Provider configuration '{provider_config_key}' referenced by specialist '{specialist_name}' not found in 'llm_providers'.")

        # This is the actual provider type, e.g., "gemini" or "lmstudio"
        base_provider_type = provider_config.get('type')

        # Look up the adapter class from the registry.
        AdapterClass = ADAPTER_REGISTRY.get(base_provider_type)
        if not AdapterClass:
            raise ValueError(f"Unknown base provider type '{base_provider_type}' specified in '{provider_config_key}'. Supported types are: {list(ADAPTER_REGISTRY.keys())}")

        # The model_config now comes directly from the llm_providers section,
        # creating a much cleaner separation of concerns.
        model_config = {
            "api_identifier": provider_config.get("api_identifier"),
            # Future-proofing for when we add parameters to the provider config
            "parameters": provider_config.get("parameters", {})
        }

        # Instantiate the correct adapter based on the provider name.
        if base_provider_type == 'gemini':
            return AdapterClass(
                model_config=model_config,
                api_key=os.getenv("GEMINI_API_KEY"),
                system_prompt=system_prompt
            )
        elif base_provider_type == 'lmstudio':
            return AdapterClass(
                model_config=model_config,
                base_url=os.getenv("LMSTUDIO_BASE_URL"),
                system_prompt=system_prompt
            )

        # This line should be unreachable if the registry and the logic are in sync,
        # but it's a good safeguard against future development errors.
        raise NotImplementedError(f"Provider type '{base_provider_type}' is registered but not implemented in the AdapterFactory.")