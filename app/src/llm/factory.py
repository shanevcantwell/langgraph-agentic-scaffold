# app/src/llm/factory.py
import logging
from typing import Dict, Any, List, Tuple
from .adapter import BaseAdapter
from .adapters import GeminiAdapter, LMStudioAdapter # Import all possible adapters
from .gemini_webui_adapter import GeminiWebUIAdapter # Distillation adapter

logger = logging.getLogger(__name__)

# --- Adapter Registry ---
# This mapping provides a robust, explicit link between the provider name
# in config.yaml and the corresponding adapter class. It avoids brittle
# string manipulation and makes the factory easily extensible.
ADAPTER_REGISTRY = {
    "gemini": GeminiAdapter,
    "lmstudio": LMStudioAdapter,
    "gemini_webui": GeminiWebUIAdapter,  # Web UI adapter for distillation (ADR-DISTILL-006)
    # "ollama": OllamaAdapter, # Example for future extension
}

# --- Provider Dependency Requirements ---
# Maps provider types to their optional dependencies and installation instructions
PROVIDER_DEPENDENCIES = {
    "gemini_webui": {
        "packages": ["playwright"],
        "check": lambda: _check_playwright_available(),
        "install_cmd": "pip install playwright && playwright install chromium",
        "description": "Playwright (for browser automation to extract thinking blocks)"
    },
}

def _check_playwright_available() -> bool:
    """Check if Playwright is installed and browsers are available."""
    try:
        from playwright.sync_api import sync_playwright
        # Try to verify browser installation
        with sync_playwright() as p:
            # Just checking if chromium executable exists
            return True
    except ImportError:
        return False
    except Exception:
        # Playwright installed but browsers not installed
        return False

class AdapterFactory:
    def __init__(self, full_config: Dict[str, Any]):
        self.full_config = full_config

    def validate_provider_dependencies(self) -> List[Tuple[str, str, str]]:
        """
        Validate that all bound providers have their required dependencies installed.

        Returns:
            List of tuples (provider_key, provider_type, error_message) for missing dependencies
        """
        missing_deps = []

        # Get all bound providers (those actually being used by specialists)
        bound_providers = set()
        for specialist_name, specialist_config in self.full_config.get("specialists", {}).items():
            if specialist_config.get("type") in ["llm", "hybrid"]:
                binding_key = specialist_config.get("llm_config")
                if binding_key:
                    bound_providers.add(binding_key)

        # Check each bound provider
        for provider_key in bound_providers:
            provider_config = self.full_config.get("llm_providers", {}).get(provider_key)
            if not provider_config:
                continue

            provider_type = provider_config.get("type")

            # Check if this provider type has dependency requirements
            if provider_type in PROVIDER_DEPENDENCIES:
                dep_info = PROVIDER_DEPENDENCIES[provider_type]

                # Run the availability check
                if not dep_info["check"]():
                    error_msg = (
                        f"Provider '{provider_key}' (type: {provider_type}) requires {dep_info['description']} "
                        f"but it is not available.\n"
                        f"   Install with: {dep_info['install_cmd']}"
                    )
                    missing_deps.append((provider_key, provider_type, error_msg))
                    logger.warning(error_msg)

        return missing_deps

    def create_adapter(self, specialist_name: str, system_prompt: str) -> BaseAdapter | None:
        """
        Creates an LLM adapter based on a provider binding key from the configuration.
        """
        logger.debug(f"AdapterFactory: Received request to create adapter for specialist_name='{specialist_name}'.")
        if not specialist_name:
            raise ValueError("Cannot create adapter: 'specialist_name' was not provided.")

        specialist_config = self.full_config.get("specialists", {}).get(specialist_name)
        specialist_type = specialist_config.get("type") if specialist_config else None

        if specialist_type not in ["llm", "hybrid"]:
            logger.debug(f"AdapterFactory: Specialist '{specialist_name}' is of type '{specialist_type}', no LLM adapter will be created. Returning None.")
            return None

        binding_key = specialist_config.get("llm_config")
        if not binding_key:
            raise ValueError(f"LLM specialist '{specialist_name}' is missing 'llm_config' key.")
        logger.debug(f"AdapterFactory: Found binding key '{binding_key}' for specialist '{specialist_name}'.")

        # Get the full provider configuration block from the top-level `llm_providers`
        provider_config = self.full_config.get("llm_providers", {}).get(binding_key)
        if not provider_config:
            raise ValueError(f"Provider '{binding_key}' for specialist '{specialist_name}' not found in 'llm_providers'.")
        
        logger.debug(f"AdapterFactory: Full provider config for '{binding_key}': {provider_config}")
        
        # Add the binding key to the config for better error messages within the adapter.
        provider_config['binding_key'] = binding_key

        # This is the actual provider type, e.g., "gemini" or "lmstudio"
        base_provider_type = provider_config.get('type')
        AdapterClass = ADAPTER_REGISTRY.get(base_provider_type)
        if not AdapterClass:
            logger.error(f"AdapterFactory: Unknown base provider type '{base_provider_type}' specified in '{binding_key}'. Supported types are: {list(ADAPTER_REGISTRY.keys())}")
            return None

        # Use the adapter's own factory method to create the instance.
        adapter = AdapterClass.from_config(provider_config, system_prompt)
        if not adapter:
            logger.error(f"AdapterFactory: AdapterClass.from_config for '{base_provider_type}' returned None.")
        return adapter