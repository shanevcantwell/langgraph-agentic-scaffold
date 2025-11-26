import pytest
import os
from src.llm.factory import AdapterFactory
from src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage
from src.utils.config_loader import ConfigLoader

@pytest.mark.live_llm
@pytest.mark.xfail(reason="Google Gemini API quota/billing issues. Awaiting future API plans.")
def test_live_gemini_adapter_interaction():
    """Tests a basic interaction with a live Gemini model via the AdapterFactory."""
    if not os.getenv("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY not set. Skipping live Gemini test.")

    try:
        # Load the base config, then programmatically override it to ensure this
        # test always targets a Gemini provider, regardless of user_settings.yaml.
        config = ConfigLoader().get_config()
        specialist_name_to_test = "systems_architect"
        provider_name_to_test = "gemini_flash" # Must be a provider of type 'gemini'

        # Force the binding for this test run
        config["specialists"][specialist_name_to_test]["llm_config"] = provider_name_to_test
        # Instantiate the factory with the loaded config
        factory = AdapterFactory(config)
        adapter = factory.create_adapter(
            specialist_name="systems_architect",
            system_prompt="You are a helpful assistant."
        )

        assert adapter is not None, "Adapter creation failed."

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello, what is your name?")]
        )

        response = adapter.invoke(request)

        assert "text_response" in response
        assert response["text_response"] is not None
        assert isinstance(response["text_response"], str)
        assert len(response["text_response"]) > 0
        print(f"\nLive Gemini Response: {response['text_response']}")

    except Exception as e:
        # Skip on API permission/auth errors (blocked key, invalid key, etc.)
        error_msg = str(e).lower()
        if any(term in error_msg for term in ["permission", "blocked", "403", "401", "unauthorized", "api_key"]):
            pytest.skip(f"Gemini API not accessible (permission/auth error): {e}")
        pytest.fail(f"Live LLM test failed: {e}")
