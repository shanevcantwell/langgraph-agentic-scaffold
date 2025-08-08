import pytest
from langchain_core.messages import AIMessage
from src.specialists.router_specialist import router_specialist
from src.state import AgentState

def test_router_happy_path(mocker):
    """Tests correct routing on valid LLM response."""
    mock_response = AIMessage(content='```json\n{"next_specialist": "data_extractor_specialist"}\n```')
    mocker.patch("langchain_google_genai.chat_models.ChatGoogleGenerativeAI.invoke", return_value=mock_response)
    
    state = AgentState(messages=["Extract data for me"])
    result = router_specialist(state)
    
    assert result == {"next_specialist": "data_extractor_specialist"}

def test_router_fallback_on_malformed_response(mocker):
    """Tests fallback routing on non-JSON LLM response."""
    mock_response = AIMessage(content="I am not sure.")
    mocker.patch("langchain_google_genai.chat_models.ChatGoogleGenerativeAI.invoke", return_value=mock_response)
    
    state = AgentState(messages=["Gibberish"])
    result = router_specialist(state)
    
    assert result == {"next_specialist": "prompt_specialist"}
