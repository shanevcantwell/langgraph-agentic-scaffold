import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.default_responder_specialist import DefaultResponderSpecialist
from app.src.llm.adapter import StandardizedLLMRequest

@pytest.fixture
def default_responder_specialist(initialized_specialist_factory):
    """Fixture for an initialized DefaultResponderSpecialist."""
    return initialized_specialist_factory("DefaultResponderSpecialist")

def test_default_responder_generates_response_and_completes_task(default_responder_specialist):
    """Tests that the specialist generates a response and signals task completion."""
    # Arrange
    mock_llm_response_content = "Hello, I am a default responder."
    default_responder_specialist.llm_adapter.invoke.return_value = {
        "text_response": mock_llm_response_content
    }

    initial_state = {
        "messages": [
            HumanMessage(content="Hi there!"),
            AIMessage(content="I am a router.", name="router_specialist"), # Should be filtered out
            AIMessage(content="Previous default response.", name="default_responder_specialist") # Should be included
        ]
    }

    # Act
    result_state = default_responder_specialist._execute_logic(initial_state)

    # Assert
    default_responder_specialist.llm_adapter.invoke.assert_called_once()
    # Check that the messages passed to LLM are filtered correctly
    called_request = default_responder_specialist.llm_adapter.invoke.call_args[0][0]
    assert isinstance(called_request, StandardizedLLMRequest)
    assert len(called_request.messages) == 2 # HumanMessage and previous AIMessage from self
    assert called_request.messages[0].content == "Hi there!"
    assert called_request.messages[1].content == "Previous default response."

    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_llm_response_content
    assert result_state["messages"][0].name == "default_responder_specialist"
    assert "task_is_complete" not in result_state

def test_default_responder_handles_empty_llm_response(default_responder_specialist):
    """Tests that the specialist provides a fallback message if LLM returns empty."""
    # Arrange
    default_responder_specialist.llm_adapter.invoke.return_value = {
        "text_response": "",
        "raw_response_content": "LLM returned nothing useful."
    }

    initial_state = {"messages": [HumanMessage(content="Say something.")]}

    # Act
    result_state = default_responder_specialist._execute_logic(initial_state)

    # Assert
    default_responder_specialist.llm_adapter.invoke.assert_called_once()
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I was unable to provide a response." in result_state["messages"][0].content
    assert "LLM returned nothing useful." in result_state["messages"][0].content
    assert "task_is_complete" not in result_state

def test_default_responder_filters_messages_correctly(default_responder_specialist):
    """Tests that only HumanMessage and its own AIMessages are passed to the LLM."""
    # Arrange
    default_responder_specialist.llm_adapter.invoke.return_value = {"text_response": "Filtered response."}
    initial_state = {
        "messages": [HumanMessage(content="User query 1"), AIMessage(content="Router thought", name="router_specialist"), AIMessage(content="Default responder's previous turn", name="default_responder_specialist"), HumanMessage(content="User query 2"), AIMessage(content="Another specialist's output", name="other_specialist")]
    }
    # Act
    default_responder_specialist._execute_logic(initial_state)
    # Assert
    called_request = default_responder_specialist.llm_adapter.invoke.call_args[0][0]
    assert isinstance(called_request, StandardizedLLMRequest)
    assert len(called_request.messages) == 3
    assert called_request.messages[0].content == "User query 1"
    assert called_request.messages[0].type == "human"
    assert called_request.messages[1].content == "Default responder's previous turn"
    assert called_request.messages[1].type == "ai"
    assert called_request.messages[1].name == "default_responder_specialist"
    assert called_request.messages[2].content == "User query 2"
    assert called_request.messages[2].type == "human"