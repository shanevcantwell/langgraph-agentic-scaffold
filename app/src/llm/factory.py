import os
from ..utils.config_loader import ConfigLoader
from .adapter import BaseAdapter
from .adapters import GeminiAdapter, LMStudioAdapter # Import all possible adapters

class AdapterFactory:
    def create_adapter(self, specialist_name: str, system_prompt: str) -> BaseAdapter:
        config = ConfigLoader()
        
        spec_config = config.get_specialist_config(specialist_name)
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
        elif adapter_class_name == 'OllamaAdapter':
            return OllamaAdapter(
                model_config=model_config,
                provider_config=provider_config,
                base_url=os.getenv("OLLAMA_BASE_URL"),
                system_prompt=system_prompt
            )
        # Add future adapters here (e.g., ClaudeAdapter)
        
        raise ValueError(f"Unknown adapter class '{adapter_class_name}'")
