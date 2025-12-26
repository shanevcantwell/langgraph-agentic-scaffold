# app/tests/unit/test_progenitor_alpha_specialist.py
"""
Unit tests for ProgenitorAlphaSpecialist - provides analytical perspective in tiered chat.

Part of CORE-CHAT-002 implementation.
"""
import pytest
from unittest.mock import MagicMock, ANY
from langchain_core.messages import AIMessage, HumanMessage


@pytest.fixture
def progenitor_alpha(initialized_specialist_factory):
    """Fixture to provide an initialized ProgenitorAlphaSpecialist."""
    return initialized_specialist_factory("ProgenitorAlphaSpecialist")


def test_progenitor_alpha_initialization(progenitor_alpha):
    """Verifies that ProgenitorAlphaSpecialist initializes correctly."""
    assert progenitor_alpha.specialist_name == "progenitor_alpha_specialist"
    assert progenitor_alpha.llm_adapter is not None


def test_progenitor_alpha_generates_analytical_response(progenitor_alpha):
    """Tests that ProgenitorAlpha generates an analytical perspective response."""
    # Arrange
    mock_response = "**Analytical Definition**: Python is a high-level, interpreted programming language..."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # LLM adapter should be called once
    progenitor_alpha.llm_adapter.invoke.assert_called_once_with(ANY)

    # CRITICAL STATE MANAGEMENT: Progenitors should NOT append to messages
    # Only TieredSynthesizer (join node) appends to messages
    assert "messages" not in result_state

    # Response should be stored in artifacts only
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["alpha_response.md"] == mock_response


def test_progenitor_alpha_stores_response_in_artifacts(progenitor_alpha):
    """Tests that ProgenitorAlpha stores response in artifacts.alpha_response.md."""
    # Arrange
    mock_response = "Structured analytical response about Python."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # CRITICAL: Response must be in artifacts.alpha_response.md for TieredSynthesizer
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["alpha_response.md"] == mock_response


def test_progenitor_alpha_does_not_set_task_complete(progenitor_alpha):
    """Tests that ProgenitorAlpha does NOT set task_is_complete (TieredSynthesizer does)."""
    # Arrange
    mock_response = "Analytical response."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="Test")]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # Should NOT set task_is_complete - the TieredSynthesizer sets it
    assert "task_is_complete" not in result_state
    # OR if it's in the result, it should be False or None
    assert result_state.get("task_is_complete") in [None, False]


def test_progenitor_alpha_maintains_conversation_context(progenitor_alpha):
    """Tests that ProgenitorAlpha sends full conversation history to LLM."""
    # Arrange
    mock_response = "Analytical follow-up response."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Simulate multi-turn conversation
    initial_state = {
        "messages": [
            HumanMessage(content="What is Python?"),
            AIMessage(content="Python is a programming language.", name="progenitor_alpha_specialist"),
            HumanMessage(content="Who created it?")
        ]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # The LLM should receive the full message history for context
    call_args = progenitor_alpha.llm_adapter.invoke.call_args
    request = call_args[0][0]
    assert len(request.messages) == 3  # All three messages should be passed


def test_progenitor_alpha_handles_llm_failure_gracefully(progenitor_alpha):
    """Tests that ProgenitorAlpha provides fallback message when LLM fails."""
    # Arrange
    # Simulate LLM returning no text_response
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": None}

    initial_state = {
        "messages": [HumanMessage(content="Hello")]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # CRITICAL STATE MANAGEMENT: Progenitors should NOT append to messages
    assert "messages" not in result_state

    # Fallback should still be stored in artifacts
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"]
    assert "unable to provide a response" in result_state["artifacts"]["alpha_response.md"].lower()


def test_progenitor_alpha_stores_content_in_artifacts(progenitor_alpha):
    """Tests that ProgenitorAlpha stores response content in artifacts (state management)."""
    # Arrange
    mock_response = "Analytical test response."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}
    progenitor_alpha.llm_adapter.model_name = "test-analytical-model"

    initial_state = {
        "messages": [HumanMessage(content="Test question")]
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # CRITICAL STATE MANAGEMENT: Progenitors should NOT append to messages
    assert "messages" not in result_state

    # Response should be in artifacts
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["alpha_response.md"] == mock_response


def test_progenitor_alpha_handles_empty_message_history(progenitor_alpha):
    """Tests that ProgenitorAlpha handles edge case of empty message history."""
    # Arrange
    mock_response = "Analytical response to empty context."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": []
    }

    # Act
    result_state = progenitor_alpha._execute_logic(initial_state)

    # Assert
    # CRITICAL STATE MANAGEMENT: Progenitors should NOT append to messages
    assert "messages" not in result_state

    # Should still process successfully and store in artifacts
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["alpha_response.md"] == mock_response


def test_progenitor_alpha_artifact_key_has_md_extension(progenitor_alpha):
    """
    Verifies that ProgenitorAlpha saves with .md extension for proper archival.

    REQUIREMENT: Progenitor responses must use .md extension (e.g., alpha_response.md)
    so the archiver can properly save them as markdown files. Without the extension,
    the archiver cannot determine the correct content type.
    """
    mock_response = "# Analysis\n\nPython is a programming language."
    progenitor_alpha.llm_adapter.invoke.return_value = {"text_response": mock_response}

    initial_state = {
        "messages": [HumanMessage(content="What is Python?")]
    }

    result_state = progenitor_alpha._execute_logic(initial_state)

    # CRITICAL: artifact key should have .md extension for proper archival
    assert "artifacts" in result_state
    assert "alpha_response.md" in result_state["artifacts"], (
        "Progenitor Alpha should save with .md extension: 'alpha_response.md'"
    )
    assert result_state["artifacts"]["alpha_response.md"] == mock_response
