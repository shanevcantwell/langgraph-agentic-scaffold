import pytest
import os
from src.llm.factory import AdapterFactory
from src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage
from src.utils.config_loader import ConfigLoader

@pytest.mark.live_llm
def test_live_gemini_adapter_interaction():
    """Tests a basic interaction with a live Gemini model via the AdapterFactory."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set. Skipping live Gemini test.")

    try:
        # Manually load the config, which now resolves env vars. This keeps the
        # test integrated with the actual config files.
        config = ConfigLoader().get_config()

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
        pytest.fail(f"Live LLM test failed: {e}")
