# app/src/llm/factory.py
import asyncio
import logging
import threading
import time
from typing import Dict, Any, List, Optional, Tuple
from langchain_core.messages import HumanMessage
from .adapter import BaseAdapter, StandardizedLLMRequest
from .adapters import GeminiAdapter, LocalInferenceAdapter, LMStudioAdapter, PooledLocalInferenceAdapter  # Import all possible adapters
from .gemini_webui_adapter import GeminiWebUIAdapter # Distillation adapter

logger = logging.getLogger(__name__)

# --- Adapter Registry ---
# This mapping provides a robust, explicit link between the provider name
# in config.yaml and the corresponding adapter class. It avoids brittle
# string manipulation and makes the factory easily extensible.
ADAPTER_REGISTRY = {
    "gemini": GeminiAdapter,
    "local": LocalInferenceAdapter,             # Generic OpenAI-compatible local inference
    "local_pool": PooledLocalInferenceAdapter,   # Pool dispatch (inherits LMStudio quirks, harmless on non-LMS)
    "lmstudio": LMStudioAdapter,                 # LM Studio with Harmony/ref/content quirks
    "lmstudio_pool": PooledLocalInferenceAdapter, # Backward compat alias for local_pool
    "gemini_webui": GeminiWebUIAdapter,           # Web UI adapter for distillation (ADR-DISTILL-006)
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

def _run_pool_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Target function for the pool's dedicated event loop thread."""
    asyncio.set_event_loop(loop)
    loop.run_forever()


class AdapterFactory:
    def __init__(self, full_config: Dict[str, Any]):
        self.full_config = full_config
        self._pool: Optional[Any] = None  # ServerPool, typed as Any to avoid import at module level if pool not installed
        self._dispatcher: Optional[Any] = None  # ConcurrentDispatcher
        self._pool_loop: Optional[asyncio.AbstractEventLoop] = None
        self._pool_thread: Optional[threading.Thread] = None

        # Initialize shared pool if any pool providers exist
        if self._has_pool_providers():
            self._init_pool()

    def _has_pool_providers(self) -> bool:
        """Check if any llm_providers use a pool type."""
        pool_types = {"local_pool", "lmstudio_pool"}
        for provider_config in self.full_config.get("llm_providers", {}).values():
            if provider_config.get("type") in pool_types:
                return True
        return False

    def _init_pool(self) -> None:
        """Initialize the shared ServerPool, ConcurrentDispatcher, and event loop thread.

        Collects all unique LMStudio server URLs from both 'lmstudio' and 'lmstudio_pool'
        providers, so the pool knows about all available servers regardless of which
        specialists use the pooled adapter.
        """
        from local_inference_pool import ServerPool, ServerConfig, ConcurrentDispatcher

        # Collect unique servers from local inference providers, preserving api_key
        local_types = {"local", "local_pool", "lmstudio", "lmstudio_pool"}
        server_configs: dict[str, ServerConfig] = {}
        for provider_config in self.full_config.get("llm_providers", {}).values():
            if provider_config.get("type") in local_types:
                url = provider_config.get("base_url")
                if url:
                    # Strip /v1 suffix — pool manages base URLs, adapter appends /v1
                    clean_url = url.rstrip("/")
                    if clean_url.endswith("/v1"):
                        clean_url = clean_url[:-3]
                    if clean_url not in server_configs:
                        server_configs[clean_url] = ServerConfig(
                            url=clean_url,
                            api_key=provider_config.get("api_key"),
                        )

        if not server_configs:
            logger.warning("AdapterFactory: Pool providers found but no server URLs resolved. "
                           "Check LOCAL_INFERENCE_SERVERS (or LMSTUDIO_SERVERS) env var.")
            return

        # Create pool and dispatcher
        self._pool = ServerPool(list(server_configs.values()))
        self._dispatcher = ConcurrentDispatcher(self._pool)

        # Start dedicated event loop thread for async pool operations
        self._pool_loop = asyncio.new_event_loop()
        self._pool_thread = threading.Thread(
            target=_run_pool_event_loop,
            args=(self._pool_loop,),
            daemon=True,
            name="pool-event-loop"
        )
        self._pool_thread.start()

        logger.info(f"AdapterFactory: Initialized shared ServerPool with {len(server_configs)} servers: {sorted(server_configs.keys())}")

    def refresh_pool_manifests(self) -> None:
        """Refresh model manifests from all servers in the pool.

        Call this during startup (e.g., in runner pre-flight checks) to populate
        available_models on each server. Requires the pool event loop to be running.
        """
        if not self._pool or not self._pool_loop:
            return

        future = asyncio.run_coroutine_threadsafe(
            self._pool.refresh_all_manifests(),
            self._pool_loop
        )
        try:
            future.result(timeout=30)
            models = self._pool.get_all_available_models()
            logger.info(f"AdapterFactory: Pool manifest refresh complete. {len(models)} models available: {sorted(models)}")
        except Exception as e:
            logger.warning(f"AdapterFactory: Pool manifest refresh failed: {e}")

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
        llm_providers = self.full_config.get("llm_providers", {})
        provider_config = llm_providers.get(binding_key)
        if not provider_config:
            raise ValueError(f"Provider '{binding_key}' for specialist '{specialist_name}' not found in 'llm_providers'.")

        # Inject global settings from root config level into provider config
        if "max_image_size_mb" in self.full_config:
            provider_config["max_image_size_mb"] = self.full_config["max_image_size_mb"]

        logger.debug(f"AdapterFactory: Full provider config for '{binding_key}': {provider_config}")
        
        # Add the binding key to the config for better error messages within the adapter.
        provider_config['binding_key'] = binding_key

        # This is the actual provider type, e.g., "gemini" or "lmstudio"
        base_provider_type = provider_config.get('type')
        AdapterClass = ADAPTER_REGISTRY.get(base_provider_type)
        if not AdapterClass:
            logger.error(f"AdapterFactory: Unknown base provider type '{base_provider_type}' specified in '{binding_key}'. Supported types are: {list(ADAPTER_REGISTRY.keys())}")
            return None

        # ADR-CORE-068: Pooled adapters get pool/dispatcher/loop injected by factory
        if base_provider_type in ("local_pool", "lmstudio_pool"):
            if not self._pool or not self._dispatcher or not self._pool_loop:
                logger.error(
                    f"AdapterFactory: Provider '{binding_key}' uses '{base_provider_type}' but shared pool "
                    "is not initialized. Check that server URLs are configured."
                )
                return None

            model_config = {
                "api_identifier": provider_config.get("api_identifier"),
                "parameters": provider_config.get("parameters", {}),
                "context_window": provider_config.get("context_window"),
                "skip_schema_enforcement": provider_config.get("skip_schema_enforcement", False),
            }
            if "max_image_size_mb" in provider_config:
                model_config["max_image_size_mb"] = provider_config["max_image_size_mb"]

            adapter = PooledLocalInferenceAdapter(
                model_config=model_config,
                system_prompt=system_prompt,
                pool=self._pool,
                dispatcher=self._dispatcher,
                loop=self._pool_loop,
                api_key=provider_config.get("api_key"),
            )
            return adapter

        # Use the adapter's own factory method to create the instance.
        adapter = AdapterClass.from_config(provider_config, system_prompt)
        if not adapter:
            logger.error(f"AdapterFactory: AdapterClass.from_config for '{base_provider_type}' returned None.")
        return adapter


# --- LLM Connectivity Validation ---
# Simple ping to validate provider is reachable at startup

PING_PROMPT = "Reply with exactly one word: pong"
PING_SYSTEM_PROMPT = "You are a test assistant. Follow instructions exactly."


def ping_provider(provider_key: str, provider_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a simple ping to a provider and return the result.

    Used by runner._perform_pre_flight_checks() to validate connectivity at startup.

    Args:
        provider_key: The binding key (e.g., "lmstudio_router")
        provider_config: The full provider configuration dict

    Returns:
        Dict with keys: provider, type, model, success, response, error, latency_ms
    """
    result = {
        "provider": provider_key,
        "type": provider_config.get("type"),
        "model": provider_config.get("model_name", provider_config.get("api_identifier", "unknown")),
        "success": False,
        "response": None,
        "error": None,
        "latency_ms": None,
    }

    provider_type = provider_config.get("type")
    # ADR-CORE-068: For pinging, pool types use their base adapter's connectivity.
    # The pool manages slot routing at runtime; ping just validates the server is reachable.
    if provider_type in ("local_pool", "lmstudio_pool"):
        provider_type = "lmstudio" if provider_type == "lmstudio_pool" else "local"
    AdapterClass = ADAPTER_REGISTRY.get(provider_type)

    if not AdapterClass:
        result["error"] = f"Unknown provider type: {provider_type}"
        return result

    try:
        # Add binding_key for error messages
        config_copy = dict(provider_config)
        config_copy.setdefault("binding_key", provider_key)

        adapter = AdapterClass.from_config(config_copy, PING_SYSTEM_PROMPT)

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=PING_PROMPT)]
        )

        start = time.time()
        response = adapter.invoke(request)
        elapsed = (time.time() - start) * 1000

        result["latency_ms"] = round(elapsed, 1)
        result["response"] = response.get("text_response", "")[:100]  # Truncate
        result["success"] = True

    except Exception as e:
        result["error"] = str(e)[:200]  # Truncate error message

    return result