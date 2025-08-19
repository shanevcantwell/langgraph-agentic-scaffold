# app/src/llm/factory.py
import os
import logging
from ..utils.config_loader import ConfigLoader
from .adapter import BaseAdapter
from .adapters import GeminiAdapter, LMStudioAdapter # Import all possible adapters

logger = logging.getLogger(__name__)

class AdapterFactory:
    def create_adapter(self, specialist_name: str, system_prompt: str) -> BaseAdapter | None:
        config = ConfigLoader()
        spec_config = config.get_specialist_config(specialist_name)
        
        # --- FIX STARTS HERE ---
        # Check if the specialist is configured to use an LLM
        if 'model' not in spec_config or 'provider' not in spec_config:
            logger.warning(f"Specialist '{specialist_name}' is configured as LLM-optional. No adapter will be created.")
            return None
        # --- FIX ENDS HERE ---

        model_name = spec_config['model']
        provider_name = spec_config['provider']
        
        model_config = config.get_model_config(model_name)
        provider_config = config.get_provider_config(provider_name)
        adapter_class_name = provider_config['adapter_class']
        
        if adapter_class_name == 'GeminiAdapter':
            return GeminiAdapter(
                model_config=model_config,
                api_key=os.getenv("GOOGLE_API_KEY"),
                system_prompt=system_prompt
            )
        elif adapter_class_name == 'LMStudioAdapter':
            return LMStudioAdapter(
                model_config=model_config,
                base_url=os.getenv("LMSTUDIO_BASE_URL"),
                system_prompt=system_prompt
            )
        
        raise ValueError(f"Unknown adapter class '{adapter_class_name}'")