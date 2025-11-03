# app/tests/unit/test_chat_specialist.py
"""
Unit tests for ChatSpecialist - a general-purpose conversational specialist.
"""
import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def chat_specialist(initialized_specialist_factory):
    """Fixture to provide an initialized ChatSpecialist."""
    return initialized_specialist_factory("ChatSpecialist")


def test_chat_specialist_initialization(chat_specialist):
    """Verifies that ChatSpecialist initializes correctly."""
    assert chat_specialist.specialist_name == "chat_specialist"
    assert chat_specialist.llm_adapter is not None


def test_chat_specialist_processes_simple_question(chat_specialist):
    """Tests that ChatSpecialist can answer a simple question."""
    # Arrange
    mock_response = "Python is a high-level, interpreted programming language known for its readability."
    chat_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    # Act
    result_state = chat_specialist._execute_logic(initial_state)

    # Assert
    # LLM adapter should be called once
    chat_specialist.llm_adapter.invoke.assert_called_once_with(ANY)

    # Should return a single AI message
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response

    # Should add response to scratchpad for synthesis
    assert "scratchpad" in result_state
    assert "user_response_snippets" in result_state["scratchpad"]
    assert mock_response in result_state["scratchpad"]["user_response_snippets"]

    # Should mark task as complete
    assert result_state.get("task_is_complete") is True


def test_chat_specialist_maintains_conversation_context(chat_specialist):
    """Tests that ChatSpecialist sends full conversation history to LLM."""
    # Arrange
    mock_response = "That's a great follow-up question!"
    chat_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Simulate a multi-turn conversation
    initial_state = {
        "messages": [
            HumanMessage(content="What is Python?"),
            AIMessage(content="Python is a programming language.", name="chat_specialist"),
            HumanMessage(content="Who created it?")
        ]
    }

    # Act
    result_state = chat_specialist._execute_logic(initial_state)

    # Assert
    # The LLM should receive the full message history for context
    call_args = chat_specialist.llm_adapter.invoke.call_args
    request = call_args[0][0]
    assert len(request.messages) == 3  # All three messages should be passed


def test_chat_specialist_handles_llm_failure_gracefully(chat_specialist):
    """Tests that ChatSpecialist provides a fallback message when LLM fails."""
    # Arrange
    # Simulate LLM returning no text_response
    chat_specialist.llm_adapter.invoke.return_value = {"text_response": None}

    initial_state = {
        "messages": [HumanMessage(content="Hello")]
    }

    # Act
    result_state = chat_specialist._execute_logic(initial_state)

    # Assert
    # Should still return a message, using the fallback
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "unable to provide a response" in result_state["messages"][0].content.lower()


def test_chat_specialist_creates_proper_message_metadata(chat_specialist):
    """Tests that ChatSpecialist creates AIMessage with proper metadata."""
    # Arrange
    mock_response = "This is a test response."
    chat_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}
    chat_specialist.llm_adapter.model_name = "test-model"

    initial_state = {
        "messages": [HumanMessage(content="Test question")]
    }

    # Act
    result_state = chat_specialist._execute_logic(initial_state)

    # Assert
    ai_message = result_state["messages"][0]

    # Should have specialist name in the message
    assert ai_message.name == "chat_specialist"

    # Should have additional metadata
    assert "additional_kwargs" in dir(ai_message)


def test_chat_specialist_handles_empty_message_history(chat_specialist):
    """Tests that ChatSpecialist handles edge case of empty message history."""
    # Arrange
    mock_response = "Hello! How can I help you?"
    chat_specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": []
    }

    # Act
    result_state = chat_specialist._execute_logic(initial_state)

    # Assert
    # Should still process successfully
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response
