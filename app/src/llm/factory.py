# src/llm/factory.py

from .clients import BaseLLMClient, GeminiClient, OllamaClient, LMStudioClient
import os

class LLMClientFactory:
    _instances: dict = {}
    """
    A factory class to create instances of LLM clients based on a provider name.
    """
    @staticmethod
    def create_client(provider: str) -> BaseLLMClient:
        """
        Creates and returns an LLM client for the specified provider.
        Configuration is pulled from environment variables.

        Args:
            provider (str): The name of the LLM provider.
                            Supported: 'gemini', 'ollama', 'lmstudio'.

        Returns:
            BaseLLMClient: An instance of the appropriate client.

        Raises:
            ValueError: If the provider is not supported or required environment
                        variables are not set.
        """
        provider = provider.lower()
        
        if provider in LLMClientFactory._instances:
            return LLMClientFactory._instances[provider]

        client: BaseLLMClient
        if provider == "gemini":
            api_key = os.getenv("GOOGLE_API_KEY")
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set.")
            model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
            client = GeminiClient(api_key=api_key, model=model)
            
        elif provider == "ollama":
            model = os.getenv("OLLAMA_MODEL")
            if not model:
                raise ValueError("OLLAMA_MODEL environment variable not set.")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            client = OllamaClient(model=model, base_url=base_url)

        elif provider == "lmstudio":
            # The model name is sent to the OpenAI-compatible API, but often ignored by LM Studio itself.
            # It's useful for identifying which model is intended to be used.
            model = os.getenv("LMSTUDIO_MODEL", "local-model")
            base_url = os.getenv("LMSTUDIO_BASE_URL")
            if not base_url:
                raise ValueError("LMSTUDIO_BASE_URL environment variable not set.")
            client = LMStudioClient(model=model, base_url=base_url)
            
        else:
            raise ValueError(f"Unsupported LLM provider: '{provider}'. Supported providers are 'gemini', 'ollama', 'lmstudio'.")

        LLMClientFactory._instances[provider] = client
        return client
