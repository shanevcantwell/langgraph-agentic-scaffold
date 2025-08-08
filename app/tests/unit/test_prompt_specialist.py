import pytest
from langchain_core.messages import AIMessage, HumanMessage
from src.specialists.prompt_specialist import prompt_specialist
from src.state import AgentState

def test_prompt_specialist_passes_message(mocker):
    """Tests that the specialist calls the LLM and returns its message."""
    mock_response = AIMessage(content="The capital of France is Paris.")
    mocker.patch("langchain_google_genai.chat_models.ChatGoogleGenerativeAI.invoke", return_value=mock_response)
    
    state = AgentState(messages=[HumanMessage(content="What is the capital of France?")])
    result = prompt_specialist(state)
    
    # The specialist should add the AIMessage to the list of messages
    assert len(result["messages"]) == 2
    assert result["messages"][-1].content == "The capital of France is Paris."
