# app/src/llm/pooled_adapter.py
"""PooledLocalInferenceAdapter — LocalInferenceAdapter backed by a shared ServerPool (ADR-CORE-068).

Instead of each specialist owning its own OpenAI client pointing at a single server,
PooledLocalInferenceAdapter acquires a server slot from the shared pool for each request.
This prevents JIT model swap collisions and provides load balancing across servers.

The pool and dispatcher are created once by AdapterFactory and shared across all
PooledLocalInferenceAdapter instances. Each instance retains its own system prompt
and model config — only the transport (which server to hit) is shared.

Protocol fixups (Harmony stripping, $ref inlining) are inherited from
LocalInferenceAdapter and applied unconditionally.
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional

from openai import OpenAI

from local_inference_pool import ServerPool, ConcurrentDispatcher

from .adapter import StandardizedLLMRequest, LLMInvocationError
from .local_inference_adapter import LocalInferenceAdapter

logger = logging.getLogger(__name__)

# Placeholder URL used during __init__ — actual URL comes from pool at invoke time
_POOL_MANAGED_URL = "http://pool-managed"


class PooledLocalInferenceAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter backed by a shared ServerPool for slot management.

    Inherits all request formatting, schema enforcement, response parsing, and
    protocol fixups from LocalInferenceAdapter. Overrides invoke() to acquire a
    server slot from the pool, make the HTTP call, then release the slot.

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
        # Parent's __init__ creates an OpenAI client with _POOL_MANAGED_URL placeholder.
        # We discard it — pooled adapters create per-request clients in invoke().
        self.client = None

        logger.info(
            f"INITIALIZED PooledLocalInferenceAdapter for model '{self.model_name}' "
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
                f"PooledLocalInferenceAdapter: Timed out waiting for server slot "
                f"for model '{model_id}' after {self.timeout}s"
            )

        try:
            # Build kwargs using parent's method (protocol fixups applied unconditionally)
            api_kwargs = self._build_request_kwargs(request)
            start_time = time.perf_counter()

            # Create client for the acquired server
            # Pool stores server-level URLs (no /v1 suffix); OpenAI SDK needs /v1
            # Use per-server api_key from pool (v0.4.0) — each server has its own token
            server_api_key = self._pool.servers[server_url].api_key or self._api_key
            client = OpenAI(base_url=f"{server_url}/v1", api_key=server_api_key)

            return self._call_with_error_handling(
                lambda: client.chat.completions.create(**api_kwargs, timeout=self.timeout),
                request, api_kwargs, start_time,
                server_url=server_url,
                on_connection_error=lambda e: self._pool.report_server_error(server_url, str(e)),
                capture_errors=False,  # Pooled path doesn't capture traces on errors (see #TBD)
            )
        finally:
            # CRITICAL: Always release the slot. A leaked slot is a silent deadlock.
            self._pool.release_server(server_url)

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "PooledLocalInferenceAdapter":
        """Not used — pool/dispatcher/loop are injected by AdapterFactory."""
        raise NotImplementedError(
            "PooledLocalInferenceAdapter is created by AdapterFactory with shared pool injection, "
            "not via from_config(). Use provider type 'local_pool' in config."
        )
