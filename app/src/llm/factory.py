import os
from typing import Optional
from .clients import BaseLLMClient, GeminiClient, OllamaClient, LMStudioClient

class LLMClientFactory:
    """
    Factory to create and configure LLM clients based on the provider.
    """
    @staticmethod
    def create_client(provider: str, system_prompt: Optional[str] = None) -> BaseLLMClient:
        """
        Creates a client for the specified LLM provider.

        Args:
            provider: The name of the LLM provider (e.g., "gemini").
            system_prompt: The system prompt to configure the model with.

        Returns:
            An instance of a BaseLLMClient subclass.
        """
        provider = provider.lower()
        
        if provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set.")
            return GeminiClient(api_key=api_key, model=model_name, system_prompt=system_prompt)
        
        elif provider == "ollama":
            model_name = os.getenv("OLLAMA_MODEL")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            if not model_name:
                raise ValueError("OLLAMA_MODEL environment variable not set.")
            return OllamaClient(model=model_name, base_url=base_url)

        elif provider == "lmstudio":
            # LM Studio doesn't have a native system prompt API, so we ignore it here.
            # The prompt will be prepended in its client implementation.
            model_name = os.getenv("LMSTUDIO_MODEL")
            base_url = os.getenv("LMSTUDIO_BASE_URL")
            if not model_name or not base_url:
                raise ValueError("LMSTUDIO_MODEL and LMSTUDIO_BASE_URL must be set.")
            return LMStudioClient(model=model_name, base_url=base_url)
            
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
