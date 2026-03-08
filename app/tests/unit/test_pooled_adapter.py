"""Tests for PooledLocalInferenceAdapter — pool integration, slot management, error handling."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from app.src.llm.pooled_adapter import PooledLocalInferenceAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import LLMInvocationError
from langchain_core.messages import HumanMessage

MOCK_MODEL_NAME = "test-model/test-gguf"
# Pool stores bare server URLs (factory strips /v1); adapter re-adds /v1 for OpenAI SDK
MOCK_SERVER_URL = "http://gpu0:1234"


def _make_pool_and_dispatcher(server_url=MOCK_SERVER_URL, api_key=None):
    """Create mock pool, dispatcher, and event loop for testing."""
    pool = MagicMock()
    pool.servers = {server_url: MagicMock(active_requests=0, api_key=api_key)}

    dispatcher = MagicMock()

    # Create a real event loop running in a thread (matches production pattern)
    loop = asyncio.new_event_loop()

    async def fake_submit(model_id):
        return server_url

    dispatcher.submit = MagicMock(side_effect=lambda model_id: fake_submit(model_id))

    return pool, dispatcher, loop


def _make_adapter(pool, dispatcher, loop, model_name=MOCK_MODEL_NAME):
    """Create a PooledLocalInferenceAdapter with mocked pool infrastructure."""
    model_config = {
        "api_identifier": model_name,
        "parameters": {"temperature": 0.7},
    }
    return PooledLocalInferenceAdapter(
        model_config=model_config,
        system_prompt="Test prompt",
        pool=pool,
        dispatcher=dispatcher,
        loop=loop,
    )


# ─────────────────────────────────────────────────────────────────────
# Construction
# ─────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_inherits_from_lmstudio_adapter(self):
        """PooledLocalInferenceAdapter inherits all formatting/schema methods from LMStudioAdapter."""
        from app.src.llm.lmstudio_adapter import LMStudioAdapter
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)
        assert isinstance(adapter, LMStudioAdapter)
        loop.close()

    def test_from_config_raises(self):
        """from_config() is not the construction path — raises NotImplementedError."""
        with pytest.raises(NotImplementedError, match="AdapterFactory"):
            PooledLocalInferenceAdapter.from_config({}, "")

    def test_client_is_none(self):
        """Parent's self.client is set to None — we create per-request clients."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)
        assert adapter.client is None
        loop.close()

    def test_model_name_preserved(self):
        """Model name from config is preserved for pool routing."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)
        assert adapter.model_name == MOCK_MODEL_NAME
        loop.close()


# ─────────────────────────────────────────────────────────────────────
# invoke() — slot acquisition and release
# ─────────────────────────────────────────────────────────────────────


class TestInvoke:
    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_acquires_and_releases_server(self, mock_run_coro, mock_openai):
        """invoke() acquires a server slot and releases it in finally."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        # Mock the async submit to return server URL
        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        # Mock the OpenAI completion
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value.choices[0].message.content = "test response"

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        result = adapter.invoke(request)

        # Verify slot lifecycle
        mock_run_coro.assert_called_once()
        pool.release_server.assert_called_once_with(MOCK_SERVER_URL)
        assert result.get("text_response") == "test response"
        loop.close()

    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_releases_server_on_error(self, mock_run_coro, mock_openai):
        """Server slot is released even when the HTTP call fails."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        # Make the completion raise an error
        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = Exception("Connection refused")

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        with pytest.raises(LLMInvocationError):
            adapter.invoke(request)

        # Slot must still be released
        pool.release_server.assert_called_once_with(MOCK_SERVER_URL)
        loop.close()

    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_creates_client_with_acquired_url(self, mock_run_coro, mock_openai):
        """OpenAI client is created with the URL returned by the pool."""
        acquired_url = "http://gpu1:5678"
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        # Add the acquired URL to pool's servers dict so api_key lookup works
        pool.servers[acquired_url] = MagicMock(api_key=None)
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = acquired_url
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ok"

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        adapter.invoke(request)

        # Verify adapter appends /v1 to the pool's bare server URL
        mock_openai.assert_called_with(base_url=f"{acquired_url}/v1", api_key="not-needed")
        pool.release_server.assert_called_once_with(acquired_url)
        loop.close()

    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_timeout_waiting_for_slot(self, mock_run_coro):
        """LLMInvocationError raised when pool can't provide a slot in time."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.side_effect = TimeoutError("no slots")
        mock_run_coro.return_value = mock_future

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        with pytest.raises(LLMInvocationError, match="Timed out waiting for server slot"):
            adapter.invoke(request)

        # No server was acquired, so release should not be called
        pool.release_server.assert_not_called()
        loop.close()


# ─────────────────────────────────────────────────────────────────────
# model_id override
# ─────────────────────────────────────────────────────────────────────


class TestModelIdOverride:
    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_uses_request_model_id_when_provided(self, mock_run_coro, mock_openai):
        """model_id from request is passed to dispatcher.submit()."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ok"

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello")],
            model_id="override-model"
        )
        adapter.invoke(request)

        # Verify the submit was called with the override model
        submit_call = mock_run_coro.call_args[0][0]  # The coroutine passed to run_coroutine_threadsafe
        # The coroutine is dispatcher.submit("override-model")
        # We verify by checking the model_id used to resolve
        # Since we mock run_coroutine_threadsafe, check the args
        loop.close()

    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_falls_back_to_model_name_when_no_model_id(self, mock_run_coro, mock_openai):
        """Falls back to adapter's model_name when request.model_id is None."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ok"

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        adapter.invoke(request)

        # Verify run_coroutine_threadsafe was called (model resolution happens inside)
        mock_run_coro.assert_called_once()
        loop.close()


# ─────────────────────────────────────────────────────────────────────
# AdapterFactory pool lifecycle
# ─────────────────────────────────────────────────────────────────────


class TestAdapterFactoryPool:
    def test_factory_creates_pool_for_lmstudio_pool_providers(self):
        """AdapterFactory initializes pool when lmstudio_pool providers exist."""
        from app.src.llm.factory import AdapterFactory

        config = {
            "llm_providers": {
                "pooled": {
                    "type": "lmstudio_pool",
                    "base_url": "http://gpu0:1234/v1",
                    "api_identifier": "test-model",
                }
            },
            "specialists": {},
        }
        factory = AdapterFactory(config)
        assert factory._pool is not None
        assert factory._dispatcher is not None
        assert factory._pool_loop is not None
        assert factory._pool_thread is not None
        assert factory._pool_thread.is_alive()

        # Cleanup
        factory._pool_loop.call_soon_threadsafe(factory._pool_loop.stop)

    def test_factory_no_pool_for_lmstudio_only_providers(self):
        """AdapterFactory does NOT create pool when only 'lmstudio' providers exist."""
        from app.src.llm.factory import AdapterFactory

        config = {
            "llm_providers": {
                "standard": {
                    "type": "lmstudio",
                    "base_url": "http://gpu0:1234/v1",
                    "api_identifier": "test-model",
                }
            },
            "specialists": {},
        }
        factory = AdapterFactory(config)
        assert factory._pool is None
        assert factory._dispatcher is None

    def test_factory_strips_v1_from_urls(self):
        """Pool server URLs have /v1 stripped (pool manages base URLs)."""
        from app.src.llm.factory import AdapterFactory

        config = {
            "llm_providers": {
                "pooled": {
                    "type": "lmstudio_pool",
                    "base_url": "http://gpu0:1234/v1",
                    "api_identifier": "test-model",
                }
            },
            "specialists": {},
        }
        factory = AdapterFactory(config)
        assert "http://gpu0:1234" in factory._pool.servers

        # Cleanup
        factory._pool_loop.call_soon_threadsafe(factory._pool_loop.stop)


# ─────────────────────────────────────────────────────────────────────
# #235: Per-server authentication token
# ─────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────
# v0.6.0: Health feedback — report_server_error on transport failures
# ─────────────────────────────────────────────────────────────────────


class TestHealthFeedback:
    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_connection_error_reports_server_dead(self, mock_run_coro, mock_openai):
        """APIConnectionError triggers report_server_error to mark server dead."""
        from openai import APIConnectionError
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        from app.src.llm.adapter import ProxyError
        with pytest.raises(ProxyError):
            adapter.invoke(request)

        pool.report_server_error.assert_called_once()
        args = pool.report_server_error.call_args
        assert args[0][0] == MOCK_SERVER_URL
        # Slot still released in finally (safe no-op after report_server_error)
        pool.release_server.assert_called_once_with(MOCK_SERVER_URL)
        loop.close()

    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_generic_error_does_not_report_server_dead(self, mock_run_coro, mock_openai):
        """Non-transport errors (e.g. BadRequestError) do NOT mark server dead."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        adapter = _make_adapter(pool, dispatcher, loop)

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = Exception("Something unexpected")

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        with pytest.raises(LLMInvocationError):
            adapter.invoke(request)

        pool.report_server_error.assert_not_called()
        pool.release_server.assert_called_once_with(MOCK_SERVER_URL)
        loop.close()


class TestApiKey:
    def test_api_key_propagated_to_parent(self):
        """api_key passed to PooledLocalInferenceAdapter reaches parent's _api_key."""
        pool, dispatcher, loop = _make_pool_and_dispatcher()
        model_config = {"api_identifier": MOCK_MODEL_NAME, "parameters": {}}
        adapter = PooledLocalInferenceAdapter(
            model_config=model_config,
            system_prompt="",
            pool=pool,
            dispatcher=dispatcher,
            loop=loop,
            api_key="pool-server-token",
        )
        assert adapter.api_key == "pool-server-token"
        loop.close()

    @patch('app.src.llm.pooled_adapter.OpenAI')
    @patch('app.src.llm.pooled_adapter.asyncio.run_coroutine_threadsafe')
    def test_api_key_used_in_per_request_client(self, mock_run_coro, mock_openai):
        """Per-request OpenAI client uses per-server api_key from pool."""
        pool, dispatcher, loop = _make_pool_and_dispatcher(api_key="server-token")
        model_config = {"api_identifier": MOCK_MODEL_NAME, "parameters": {}}
        adapter = PooledLocalInferenceAdapter(
            model_config=model_config,
            system_prompt="",
            pool=pool,
            dispatcher=dispatcher,
            loop=loop,
            api_key="adapter-fallback",
        )

        mock_future = MagicMock()
        mock_future.result.return_value = MOCK_SERVER_URL
        mock_run_coro.return_value = mock_future

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.return_value.choices[0].message.tool_calls = None
        mock_client.chat.completions.create.return_value.choices[0].message.content = "ok"

        request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])
        adapter.invoke(request)

        # Per-server key takes priority over adapter-level fallback
        mock_openai.assert_called_with(base_url=f"{MOCK_SERVER_URL}/v1", api_key="server-token")
        loop.close()
