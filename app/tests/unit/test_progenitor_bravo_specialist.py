# app/tests/unit/test_progenitor_bravo_specialist.py
"""
Unit tests for ProgenitorBravoSpecialist - provides contextual perspective in tiered chat.

Part of CORE-CHAT-002 implementation.
"""
import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def progenitor_bravo(initialized_specialist_factory):
    """Fixture to provide an initialized ProgenitorBravoSpecialist."""
    return initialized_specialist_factory("ProgenitorBravoSpecialist")


def test_progenitor_bravo_initialization(progenitor_bravo):
    """Verifies that ProgenitorBravoSpecialist initializes correctly."""
    assert progenitor_bravo.specialist_name == "progenitor_bravo_specialist"
    assert progenitor_bravo.llm_adapter is not None


def test_progenitor_bravo_generates_contextual_response(progenitor_bravo):
    """Tests that ProgenitorBravo generates a contextual perspective response."""
    # Arrange
    mock_response = "Python is like a Swiss Army knife for programmers - versatile and accessible..."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # LLM adapter should be called once
    progenitor_bravo.llm_adapter.invoke.assert_called_once_with(ANY)

    # Should return a single AI message
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response
    assert result_state["messages"][0].name == "progenitor_bravo_specialist"


def test_progenitor_bravo_stores_response_in_artifacts(progenitor_bravo):
    """Tests that ProgenitorBravo stores response in artifacts.bravo_response."""
    # Arrange
    mock_response = "Contextual, intuitive response about Python."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # CRITICAL: Response must be in artifacts.bravo_response for TieredSynthesizer
    assert "artifacts" in result_state
    assert "bravo_response" in result_state["artifacts"]
    assert result_state["artifacts"]["bravo_response"] == mock_response


def test_progenitor_bravo_does_not_set_task_complete(progenitor_bravo):
    """Tests that ProgenitorBravo does NOT set task_is_complete (TieredSynthesizer does)."""
    # Arrange
    mock_response = "Contextual response."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Test")]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # Should NOT set task_is_complete - the TieredSynthesizer sets it
    assert "task_is_complete" not in result_state
    # OR if it's in the result, it should be False or None
    assert result_state.get("task_is_complete") in [None, False]


def test_progenitor_bravo_maintains_conversation_context(progenitor_bravo):
    """Tests that ProgenitorBravo sends full conversation history to LLM."""
    # Arrange
    mock_response = "Contextual follow-up response."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Simulate multi-turn conversation
    initial_state = {
        "messages": [
            HumanMessage(content="What is Python?"),
            AIMessage(content="Python is like a Swiss Army knife...", name="progenitor_bravo_specialist"),
            HumanMessage(content="Who created it?")
        ]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # The LLM should receive the full message history for context
    call_args = progenitor_bravo.llm_adapter.invoke.call_args
    request = call_args[0][0]
    assert len(request.messages) == 3  # All three messages should be passed


def test_progenitor_bravo_handles_llm_failure_gracefully(progenitor_bravo):
    """Tests that ProgenitorBravo provides fallback message when LLM fails."""
    # Arrange
    # Simulate LLM returning no text_response
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": None}

    initial_state = {
        "messages": [HumanMessage(content="Hello")]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # Should still return a message, using the fallback
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "unable to provide a response" in result_state["messages"][0].content.lower()

    # Fallback should still be stored in artifacts
    assert "artifacts" in result_state
    assert "bravo_response" in result_state["artifacts"]


def test_progenitor_bravo_creates_proper_message_metadata(progenitor_bravo):
    """Tests that ProgenitorBravo creates AIMessage with proper metadata."""
    # Arrange
    mock_response = "Contextual test response."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}
    progenitor_bravo.llm_adapter.model_name = "test-contextual-model"

    initial_state = {
        "messages": [HumanMessage(content="Test question")]
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    ai_message = result_state["messages"][0]

    # Should have specialist name in the message
    assert ai_message.name == "progenitor_bravo_specialist"

    # Should have additional metadata
    assert "additional_kwargs" in dir(ai_message)


def test_progenitor_bravo_handles_empty_message_history(progenitor_bravo):
    """Tests that ProgenitorBravo handles edge case of empty message history."""
    # Arrange
    mock_response = "Contextual response to empty context."
    progenitor_bravo.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": []
    }

    # Act
    result_state = progenitor_bravo._execute_logic(initial_state)

    # Assert
    # Should still process successfully
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response
    assert result_state["artifacts"]["bravo_response"] == mock_response
