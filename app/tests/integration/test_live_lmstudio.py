import pytest
import os
from src.llm.factory import AdapterFactory
from src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage

@pytest.mark.live_llm
def test_live_lmstudio_adapter_interaction():
    """Tests a basic interaction with a live LM Studio model via the AdapterFactory."""
    if not os.getenv("LMSTUDIO_BASE_URL"):
        pytest.skip("LMSTUDIO_BASE_URL environment variable not set. Skipping live LM Studio test.")

    # Mock the config to force the prompt_specialist to use the lmstudio provider
    mock_config = {
        "llm_providers": {
            "local_lmstudio": {
                "type": "lmstudio",
                "api_identifier": "local-model", # A generic identifier
                "base_url": os.getenv("LMSTUDIO_BASE_URL")
            }
        },
        "specialists": {
            "prompt_specialist": {
                "type": "llm",
                "llm_config": "local_lmstudio",
                "prompt_file": "prompt_specialist_prompt.md"
            }
        }
    }

    try:
        factory = AdapterFactory(mock_config)
        adapter = factory.create_adapter(
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
