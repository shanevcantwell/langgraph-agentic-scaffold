import pytest
import os
from src.llm.factory import AdapterFactory
from src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage
from src.utils.config_loader import ConfigLoader

@pytest.mark.live_llm
def test_live_lmstudio_adapter_interaction():
    """Tests a basic interaction with a live LM Studio model via the AdapterFactory."""
    if not os.getenv("LMSTUDIO_BASE_URL"):
        pytest.skip("LMSTUDIO_BASE_URL environment variable not set. Skipping live LM Studio test.")

    try:
        # Manually load the config, which now resolves env vars. This keeps the
        # test integrated with the actual config files.
        # Ensure your user_settings.yaml binds a specialist to an lmstudio provider.
        # For example, binding 'prompt_specialist' to 'lmstudio_specialist'.
        config = ConfigLoader().get_config()
        
        # Instantiate the factory with the loaded config
        factory = AdapterFactory(config)
        adapter = factory.create_adapter(
            # This specialist must be bound to an lmstudio provider in your user_settings.yaml
            # for this test to work correctly.
            specialist_name="prompt_specialist",
            system_prompt="You are a helpful assistant."
        )

        assert adapter is not None, "Adapter creation failed for LMStudio."

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello, what is your purpose?")]
        )

        response = adapter.invoke(request)

        assert "text_response" in response
        assert response["text_response"] is not None
        assert isinstance(response["text_response"], str)
        assert len(response["text_response"]) > 0
        print(f"\nLive LMStudio Response: {response['text_response']}")

    except Exception as e:
        pytest.fail(f"Live LM Studio test failed: {e}")
