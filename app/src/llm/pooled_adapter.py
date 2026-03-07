# app/src/llm/pooled_adapter.py
"""PooledLMStudioAdapter — LMStudioAdapter backed by a shared ServerPool (ADR-CORE-068).

Instead of each specialist owning its own OpenAI client pointing at a single server,
PooledLMStudioAdapter acquires a server slot from the shared pool for each request.
This prevents JIT model swap collisions and provides load balancing across servers.

The pool and dispatcher are created once by AdapterFactory and shared across all
PooledLMStudioAdapter instances. Each instance retains its own system prompt
and model config — only the transport (which server to hit) is shared.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

from openai import OpenAI, RateLimitError as OpenAIRateLimitError, BadRequestError, APIConnectionError, PermissionDeniedError
import httpx

from local_inference_pool import ServerPool, ConcurrentDispatcher

from .adapter import StandardizedLLMRequest, LLMInvocationError, RateLimitError, ProxyError
from .lmstudio_adapter import LMStudioAdapter

logger = logging.getLogger(__name__)

# Placeholder URL used during __init__ — actual URL comes from pool at invoke time
_POOL_MANAGED_URL = "http://pool-managed"


class PooledLMStudioAdapter(LMStudioAdapter):
    """LMStudioAdapter backed by a shared ServerPool for slot management.

    Inherits all request formatting, schema enforcement, and response parsing from
    LMStudioAdapter. Overrides invoke() to acquire a server slot from the pool,
    make the HTTP call to the acquired server, then release the slot.

    Construction is handled by AdapterFactory, not from_config().
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        system_prompt: str,
        pool: ServerPool,
        dispatcher: ConcurrentDispatcher,
        loop: asyncio.AbstractEventLoop,
        api_key: Optional[str] = None,
    ):
        # Initialize parent with placeholder URL — we override invoke() to use pool
        super().__init__(model_config=model_config, base_url=_POOL_MANAGED_URL, system_prompt=system_prompt, api_key=api_key)
        self._pool = pool
        self._dispatcher = dispatcher
        self._loop = loop
        # Don't use parent's self.client — we create per-request clients
        self.client = None

        logger.info(
            f"INITIALIZED PooledLMStudioAdapter for model '{self.model_name}' "
            f"with shared pool ({len(pool.servers)} servers)."
        )

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """Acquire a server slot, make the HTTP call, release the slot.

        Uses run_coroutine_threadsafe to bridge sync invoke() to the pool's
        async dispatcher, following the BaseDispatcher.dispatch_sync() pattern.
        """
        model_id = getattr(request, 'model_id', None) or self.model_name

        # Acquire server slot via async dispatcher (sync→async bridge)
        future = asyncio.run_coroutine_threadsafe(
            self._dispatcher.submit(model_id),
            self._loop
        )
        try:
            server_url = future.result(timeout=self.timeout)
        except TimeoutError:
            raise LLMInvocationError(
                f"PooledLMStudioAdapter: Timed out waiting for server slot "
                f"for model '{model_id}' after {self.timeout}s"
            )

        try:
            # Build kwargs using parent's extracted method
            api_kwargs = self._build_request_kwargs(request)
            start_time = time.perf_counter()

            try:
                # Create client for the acquired server
                # Pool stores server-level URLs (no /v1 suffix); OpenAI SDK needs /v1
                # Use per-server api_key from pool (v0.4.0) — each server has its own token
                server_api_key = self._pool.servers[server_url].api_key or self._api_key
                client = OpenAI(base_url=f"{server_url}/v1", api_key=server_api_key)
                completion = client.chat.completions.create(**api_kwargs, timeout=self.timeout)
                return self._parse_completion(completion, request, api_kwargs, start_time)

            except OpenAIRateLimitError as e:
                error_message = f"LMStudio API rate limit exceeded on {server_url}: {e}"
                logger.error(error_message, exc_info=True)
                raise RateLimitError(error_message) from e

            except (APIConnectionError, PermissionDeniedError, httpx.ProxyError) as e:
                self._pool.report_server_error(server_url, str(e))
                clean_message = (
                    f"A network error occurred connecting to {server_url}. "
                    "This is often due to a proxy blocking the request. "
                    "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
                )
                logger.error(f"{clean_message} Original error: {e}", exc_info=True)
                raise ProxyError(clean_message) from e

            except BadRequestError as e:
                if "context length" in str(e).lower():
                    error_message = (
                        f"LMStudio API context length error on {server_url}: {e}. "
                        "This can happen if the configured 'context_window' is too large for the loaded model."
                    )
                    logger.error(error_message, exc_info=True)
                    raise LLMInvocationError(error_message) from e
                else:
                    logger.error(f"LMStudio API BadRequestError on {server_url}: {e}", exc_info=True)
                    raise LLMInvocationError(f"LMStudio API BadRequestError: {e}") from e

            except Exception as e:
                logger.error(f"LMStudio API error on {server_url}: {e}", exc_info=True)
                raise LLMInvocationError(f"LMStudio API error: {e}") from e
        finally:
            # CRITICAL: Always release the slot. A leaked slot is a silent deadlock.
            self._pool.release_server(server_url)

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "PooledLMStudioAdapter":
        """Not used — pool/dispatcher/loop are injected by AdapterFactory."""
        raise NotImplementedError(
            "PooledLMStudioAdapter is created by AdapterFactory with shared pool injection, "
            "not via from_config(). Use provider type 'lmstudio_pool' in config."
        )
