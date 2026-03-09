# app/src/llm/pooled_adapter.py
"""PooledLocalInferenceAdapter — LocalInferenceAdapter backed by a shared ServerPool (ADR-CORE-068).

Instead of each specialist owning its own OpenAI client pointing at a single server,
PooledLocalInferenceAdapter acquires a server slot from the shared pool for each request.
This prevents JIT model swap collisions and provides load balancing across servers.

The pool and dispatcher are created once by AdapterFactory and shared across all
PooledLocalInferenceAdapter instances. Each instance retains its own system prompt
and model config — only the transport (which server to hit) is shared.

Quirks are applied per-endpoint based on server_type (#253). After acquiring a server
slot, the adapter looks up the server's type and applies the corresponding quirk set
from server_quirks.py. This decouples transport (pool dispatch) from protocol quirks
(server-type-specific behavior).
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Any, List, Optional

from openai import OpenAI
from langchain_core.messages import BaseMessage

from local_inference_pool import ServerPool, ConcurrentDispatcher

from .adapter import StandardizedLLMRequest, LLMInvocationError
from .local_inference_adapter import LocalInferenceAdapter
from .server_quirks import get_quirks, ServerQuirks

logger = logging.getLogger(__name__)

# Placeholder URL used during __init__ — actual URL comes from pool at invoke time
_POOL_MANAGED_URL = "http://pool-managed"


class PooledLocalInferenceAdapter(LocalInferenceAdapter):
    """LocalInferenceAdapter backed by a shared ServerPool for slot management.

    Inherits all request formatting, schema enforcement, and response parsing from
    LocalInferenceAdapter. Overrides invoke() to acquire a server slot from the pool,
    look up per-server quirks, make the HTTP call to the acquired server, then release
    the slot.

    Protocol quirks (Harmony stripping, $ref inlining, schema enforcement strategy,
    thinking mode handling) are applied per-endpoint based on server_type from the pool,
    not by class inheritance.

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
        # Thread-local quirk storage — invoke() sets per-request, hooks read it.
        # Uses threading.local() (same pattern as TraceAccumulator in tracing.py)
        # so concurrent invoke() calls on the same instance can't cross-contaminate.
        self._quirks_local = threading.local()

        logger.info(
            f"INITIALIZED PooledLocalInferenceAdapter for model '{self.model_name}' "
            f"with shared pool ({len(pool.servers)} servers)."
        )

    @property
    def _active_quirks(self) -> Optional[ServerQuirks]:
        """Thread-local accessor for the current request's quirk set."""
        return getattr(self._quirks_local, 'quirks', None)

    @_active_quirks.setter
    def _active_quirks(self, value: Optional[ServerQuirks]) -> None:
        self._quirks_local.quirks = value

    # --- Hook overrides that delegate to active quirks ---

    def _preprocess_response_content(self, content: str) -> str:
        """Delegate to active quirks' preprocess_response."""
        if self._active_quirks:
            return self._active_quirks.preprocess_response(content)
        return content

    def _resolve_schema_refs(self, node: Any, defs: Dict[str, Any]) -> Any:
        """Delegate to active quirks' resolve_schema_refs."""
        if self._active_quirks:
            return self._active_quirks.resolve_schema_refs(node, defs)
        return node

    def _format_messages(
        self,
        messages: List[BaseMessage],
        use_json_tool_format: bool = False
    ) -> List[Dict[str, Any]]:
        """Format messages then apply active quirks' post-format fixups."""
        api_messages = super()._format_messages(messages, use_json_tool_format)
        if self._active_quirks:
            api_messages = self._active_quirks.format_messages_post(api_messages)
        return api_messages

    def _build_request_kwargs(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """Build request kwargs with quirk-driven schema enforcement and extra_body."""
        # Temporarily override skip_schema_enforcement based on quirks
        original_skip = self.skip_schema_enforcement
        if self._active_quirks and self._active_quirks.skip_schema_enforcement:
            self.skip_schema_enforcement = True

        api_kwargs = super()._build_request_kwargs(request)

        # Restore original value
        self.skip_schema_enforcement = original_skip

        # Merge quirk-specific extra_body injections
        if self._active_quirks:
            extra_injections = self._active_quirks.extra_body_injections()
            if extra_injections:
                existing_extra = api_kwargs.get("extra_body", {})
                existing_extra.update(extra_injections)
                api_kwargs["extra_body"] = existing_extra

        return api_kwargs

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """Acquire a server slot, apply per-server quirks, make the HTTP call, release the slot.

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
            # Look up quirks for the acquired server's type
            server_config = self._pool.servers[server_url]
            server_type = getattr(server_config, 'server_type', None)
            self._active_quirks = get_quirks(server_type)

            if server_type:
                logger.debug(f"PooledLocalInferenceAdapter: Applying '{server_type}' quirks for {server_url}")

            # Build kwargs using parent's extracted method (now quirk-aware via hooks)
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
            # Clear active quirks after request completes
            self._active_quirks = None

    @classmethod
    def from_config(cls, provider_config: Dict[str, Any], system_prompt: str) -> "PooledLocalInferenceAdapter":
        """Not used — pool/dispatcher/loop are injected by AdapterFactory."""
        raise NotImplementedError(
            "PooledLocalInferenceAdapter is created by AdapterFactory with shared pool injection, "
            "not via from_config(). Use provider type 'local_pool', 'lmstudio_pool', or 'llama_server_pool' in config."
        )
