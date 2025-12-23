# app/tests/integration/test_llm_ping.py
"""
LLM Ping Tests - Connectivity gate for live testing.

These tests verify that configured LLM providers are reachable by sending
a simple "ping" prompt and expecting a response. Use these as a gate before
running full integration tests.

Usage:
    # Run ping tests only
    pytest app/tests/integration/test_llm_ping.py -v

    # Run as pre-flight check
    pytest app/tests/integration/test_llm_ping.py -v && pytest app/tests/integration/ -v

    # Skip specific providers
    pytest app/tests/integration/test_llm_ping.py -v -k "not lmstudio"
"""
import pytest
import logging
from typing import Dict, Any, List, Tuple

from langchain_core.messages import HumanMessage

from app.src.utils.config_loader import ConfigLoader
from app.src.llm.factory import ADAPTER_REGISTRY
from app.src.llm.adapter import StandardizedLLMRequest, BaseAdapter

logger = logging.getLogger(__name__)

# Simple ping prompt - should work with any LLM
PING_PROMPT = "Reply with exactly one word: pong"
PING_SYSTEM_PROMPT = "You are a test assistant. Follow instructions exactly."


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def config() -> Dict[str, Any]:
    """Load the 3-tier merged configuration."""
    return ConfigLoader().get_config()


@pytest.fixture(scope="module")
def enabled_providers(config) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Get all enabled LLM providers from config.

    Returns list of (provider_key, provider_config) tuples.
    """
    providers = config.get("llm_providers", {})
    enabled = []

    for key, provider_config in providers.items():
        # Skip providers without a type (invalid config)
        if not provider_config.get("type"):
            logger.warning(f"Provider '{key}' has no type, skipping")
            continue

        # Skip unsupported provider types
        provider_type = provider_config.get("type")
        if provider_type not in ADAPTER_REGISTRY:
            logger.info(f"Provider '{key}' type '{provider_type}' not in registry, skipping")
            continue

        enabled.append((key, provider_config))

    return enabled


def create_adapter_direct(provider_config: Dict[str, Any], system_prompt: str) -> BaseAdapter:
    """
    Create an adapter directly from provider config (bypassing AdapterFactory specialist lookup).
    """
    provider_type = provider_config.get("type")
    AdapterClass = ADAPTER_REGISTRY.get(provider_type)

    if not AdapterClass:
        raise ValueError(f"Unknown provider type: {provider_type}")

    # Add binding_key for error messages (AdapterFactory does this)
    config_copy = dict(provider_config)
    config_copy.setdefault("binding_key", provider_type)

    return AdapterClass.from_config(config_copy, system_prompt)


def ping_provider(provider_key: str, provider_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send a ping to a provider and return the result.

    Returns:
        Dict with keys: success, response, error, latency_ms
    """
    import time

    result = {
        "provider": provider_key,
        "type": provider_config.get("type"),
        "model": provider_config.get("model_name", provider_config.get("api_identifier", "unknown")),
        "success": False,
        "response": None,
        "error": None,
        "latency_ms": None,
    }

    try:
        adapter = create_adapter_direct(provider_config, PING_SYSTEM_PROMPT)

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


# =============================================================================
# TESTS
# =============================================================================

class TestLLMPing:
    """Ping tests for LLM providers."""

    @pytest.mark.integration
    def test_config_loads_successfully(self, config):
        """Verify 3-tier config loads without error."""
        assert config is not None
        assert "llm_providers" in config

        providers = config.get("llm_providers", {})
        logger.info(f"Found {len(providers)} configured providers: {list(providers.keys())}")

        assert len(providers) > 0, "No LLM providers configured"

    @pytest.mark.integration
    def test_at_least_one_provider_available(self, enabled_providers):
        """Verify at least one provider is available for testing."""
        assert len(enabled_providers) > 0, (
            "No supported LLM providers found in config. "
            f"Supported types: {list(ADAPTER_REGISTRY.keys())}"
        )

        for key, config in enabled_providers:
            logger.info(f"  - {key}: {config.get('type')} ({config.get('model_name', 'unknown')})")


@pytest.mark.integration
class TestProviderPing:
    """Individual provider ping tests."""

    def test_ping_all_providers(self, enabled_providers):
        """
        Ping all enabled providers and report results.

        This test succeeds if AT LEAST ONE provider responds.
        Individual failures are logged but don't fail the test.
        """
        if not enabled_providers:
            pytest.skip("No enabled providers to test")

        results = []
        successes = 0

        for provider_key, provider_config in enabled_providers:
            logger.info(f"Pinging {provider_key}...")
            result = ping_provider(provider_key, provider_config)
            results.append(result)

            if result["success"]:
                successes += 1
                logger.info(
                    f"  ✓ {provider_key}: {result['latency_ms']}ms - "
                    f"'{result['response'][:50]}...'"
                )
            else:
                logger.warning(f"  ✗ {provider_key}: {result['error'][:100]}")

        # Report summary
        logger.info(f"\nPing Summary: {successes}/{len(results)} providers responded")

        # At least one must succeed
        assert successes > 0, (
            f"No LLM providers responded to ping. "
            f"Tested: {[r['provider'] for r in results]}"
        )


# =============================================================================
# INDIVIDUAL PROVIDER TESTS (for selective testing)
# =============================================================================

@pytest.mark.integration
class TestGeminiPing:
    """Ping tests specifically for Gemini providers."""

    def test_ping_gemini_providers(self, config):
        """Ping all Gemini-type providers."""
        providers = config.get("llm_providers", {})
        gemini_providers = [
            (k, v) for k, v in providers.items()
            if v.get("type") == "gemini"
        ]

        if not gemini_providers:
            pytest.skip("No Gemini providers configured")

        for provider_key, provider_config in gemini_providers:
            result = ping_provider(provider_key, provider_config)

            if not result["success"]:
                # Check for common Gemini issues
                error = result.get("error", "").lower()
                if "api_key" in error or "permission" in error or "403" in error:
                    pytest.skip(f"Gemini API not accessible: {result['error'][:100]}")

            logger.info(f"Gemini {provider_key}: {result}")


@pytest.mark.integration
class TestLMStudioPing:
    """Ping tests specifically for LMStudio providers."""

    def test_ping_lmstudio_providers(self, config):
        """Ping all LMStudio-type providers."""
        providers = config.get("llm_providers", {})
        lmstudio_providers = [
            (k, v) for k, v in providers.items()
            if v.get("type") == "lmstudio"
        ]

        if not lmstudio_providers:
            pytest.skip("No LMStudio providers configured")

        for provider_key, provider_config in lmstudio_providers:
            result = ping_provider(provider_key, provider_config)

            if not result["success"]:
                # Check for common LMStudio issues
                error = result.get("error", "").lower()
                if "connection" in error or "refused" in error or "timeout" in error:
                    pytest.skip(
                        f"LMStudio not reachable at {provider_config.get('base_url', 'unknown')}: "
                        f"{result['error'][:100]}"
                    )

            logger.info(f"LMStudio {provider_key}: {result}")


# =============================================================================
# UTILITY FUNCTIONS (can be imported by other tests)
# =============================================================================

def run_ping_check() -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Run ping check programmatically and return results.

    Returns:
        Tuple of (any_success, results_list)

    Usage:
        from app.tests.integration.test_llm_ping import run_ping_check

        success, results = run_ping_check()
        if not success:
            pytest.skip("No LLM providers available")
    """
    config = ConfigLoader().get_config()
    providers = config.get("llm_providers", {})

    results = []
    for key, provider_config in providers.items():
        provider_type = provider_config.get("type")
        if provider_type not in ADAPTER_REGISTRY:
            continue

        result = ping_provider(key, provider_config)
        results.append(result)

    any_success = any(r["success"] for r in results)
    return any_success, results


def require_llm_ping():
    """
    Pytest fixture/decorator helper to skip tests if no LLM is reachable.

    Usage:
        @pytest.fixture
        def llm_available():
            from app.tests.integration.test_llm_ping import require_llm_ping
            require_llm_ping()

        def test_something(llm_available):
            # Only runs if at least one LLM responds to ping
            ...
    """
    success, results = run_ping_check()
    if not success:
        providers_tested = [r["provider"] for r in results]
        errors = [f"{r['provider']}: {r['error'][:50]}" for r in results if r["error"]]
        pytest.skip(
            f"No LLM providers responded to ping. "
            f"Tested: {providers_tested}. Errors: {errors}"
        )


# =============================================================================
# CONFTEST INTEGRATION FIXTURE
# =============================================================================

@pytest.fixture(scope="session")
def llm_ping_gate():
    """
    Session-scoped fixture that gates on LLM availability.

    Add to conftest.py or import in tests that require live LLM:

        @pytest.fixture(scope="session")
        def llm_ping_gate():
            from app.tests.integration.test_llm_ping import run_ping_check
            success, results = run_ping_check()
            if not success:
                pytest.skip("No LLM available - ping failed")
            return results
    """
    success, results = run_ping_check()
    if not success:
        pytest.skip("No LLM available - ping failed for all providers")
    return results
