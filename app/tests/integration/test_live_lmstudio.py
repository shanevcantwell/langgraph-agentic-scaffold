import pytest
import os
from src.llm.factory import LLMClientFactory
from langchain_core.messages import HumanMessage

@pytest.mark.live_llm
def test_live_lmstudio_client_interaction():
    """Tests a basic interaction with a live LM Studio LLM client."""
    lmstudio_base_url = os.getenv("LMSTUDIO_BASE_URL")
    if not lmstudio_base_url:
        pytest.skip("LMSTUDIO_BASE_URL environment variable not set. Skipping live LM Studio test.")

    try:
        # Assuming a model named 'lmstudio-model' is loaded in LM Studio
        client = LLMClientFactory.create_client(provider="lmstudio")
        
        # Simple prompt for a basic response
        messages = [HumanMessage(content="Hello LM Studio, what is your purpose?")]
        
        response = client.invoke(messages)
        
        assert response.content is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        print(f"Live LM Studio Response: {response.content}")
        
    except Exception as e:
        pytest.fail(f"Live LM Studio test failed: {e}")
