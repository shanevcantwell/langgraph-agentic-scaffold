import pytest
from src.llm.factory import LLMClientFactory
from langchain_core.messages import HumanMessage

@pytest.mark.live_llm
def test_live_gemini_client_interaction():
    """Tests a basic interaction with the live Gemini LLM client."""
    try:
        client = LLMClientFactory.create_client(provider="gemini")
        
        # Simple prompt for a basic response
        messages = [HumanMessage(content="Hello, what is your name?")]
        
        response = client.invoke(messages)
        
        assert response.content is not None
        assert isinstance(response.content, str)
        assert len(response.content) > 0
        print(f"Live LLM Response: {response.content}")
        
    except Exception as e:
        pytest.fail(f"Live LLM test failed: {e}")
