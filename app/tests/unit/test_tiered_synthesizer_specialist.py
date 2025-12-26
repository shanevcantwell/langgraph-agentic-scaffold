# app/tests/unit/test_tiered_synthesizer_specialist.py
"""
Unit tests for TieredSynthesizerSpecialist - combines multi-perspective responses.

This is a procedural specialist (no LLM) that acts as the "join" node in the
fan-out/join pattern for CORE-CHAT-002.

Tests graceful degradation (CORE-CHAT-002.1) when one or both progenitors fail.
"""
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from app.src.graph.state_factory import create_test_state


@pytest.fixture
def tiered_synthesizer(initialized_specialist_factory):
    """Fixture to provide an initialized TieredSynthesizerSpecialist."""
    return initialized_specialist_factory("TieredSynthesizerSpecialist")


def test_tiered_synthesizer_initialization(tiered_synthesizer):
    """Verifies that TieredSynthesizerSpecialist initializes correctly."""
    assert tiered_synthesizer.specialist_name == "tiered_synthesizer_specialist"
    # Procedural specialist - should not have an LLM adapter
    assert tiered_synthesizer.llm_adapter is None or isinstance(tiered_synthesizer.llm_adapter, MagicMock)


def test_tiered_synthesizer_combines_both_responses(tiered_synthesizer):
    """Tests full tiered response when both Alpha and Bravo succeed (happy path)."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "Analytical view: Python is a high-level language...",
            "bravo_response.md": "Contextual view: Python is like a Swiss Army knife..."
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Should create a combined response
    assert "scratchpad" in result_state
    assert "user_response_snippets" in result_state["scratchpad"]
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]

    # Should contain both perspectives
    assert "Analytical View" in combined_response or "Perspective 1" in combined_response
    assert "Contextual View" in combined_response or "Perspective 2" in combined_response
    assert "Python is a high-level language" in combined_response
    assert "Swiss Army knife" in combined_response

    # Should set task_is_complete
    assert result_state.get("task_is_complete") is True

    # Should set response_mode to "tiered_full"
    assert result_state["artifacts"]["response_mode"] == "tiered_full"

    # CRITICAL: Should write final_user_response.md to skip EndSpecialist synthesis
    assert "final_user_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["final_user_response.md"] == combined_response


def test_tiered_synthesizer_handles_alpha_only(tiered_synthesizer):
    """Tests graceful degradation when only Alpha succeeds (CORE-CHAT-002.1)."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "Analytical view: Python is a high-level language..."
            # bravo_response.md is missing
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Should create a single-perspective response
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]

    # Should indicate single perspective
    assert "Single-Perspective Response" in combined_response
    assert "Analytical View" in combined_response
    assert "Python is a high-level language" in combined_response

    # Should NOT contain Bravo's content
    assert "Contextual View" not in combined_response or "missing" in combined_response.lower()

    # Should set response_mode to "tiered_alpha_only"
    assert result_state["artifacts"]["response_mode"] == "tiered_alpha_only"

    # Should still set task_is_complete
    assert result_state.get("task_is_complete") is True

    # Should still write final_user_response.md
    assert "final_user_response.md" in result_state["artifacts"]


def test_tiered_synthesizer_handles_bravo_only(tiered_synthesizer):
    """Tests graceful degradation when only Bravo succeeds (CORE-CHAT-002.1)."""
    # Arrange
    initial_state = {
        "artifacts": {
            # alpha_response.md is missing
            "bravo_response.md": "Contextual view: Python is like a Swiss Army knife..."
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Should create a single-perspective response
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]

    # Should indicate single perspective
    assert "Single-Perspective Response" in combined_response
    assert "Contextual View" in combined_response
    assert "Swiss Army knife" in combined_response

    # Should NOT contain Alpha's content
    assert "Analytical View" not in combined_response or "missing" in combined_response.lower()

    # Should set response_mode to "tiered_bravo_only"
    assert result_state["artifacts"]["response_mode"] == "tiered_bravo_only"

    # Should still set task_is_complete
    assert result_state.get("task_is_complete") is True

    # Should still write final_user_response.md
    assert "final_user_response.md" in result_state["artifacts"]


def test_tiered_synthesizer_raises_error_when_both_missing(tiered_synthesizer):
    """Tests that TieredSynthesizer raises error when both progenitors fail."""
    # Arrange
    initial_state = {
        "artifacts": {
            # Both alpha_response.md and bravo_response.md are missing
        },
        "messages": []
    }

    # Act & Assert
    # Should raise ValueError when both responses are missing
    with pytest.raises(ValueError) as exc_info:
        tiered_synthesizer._execute_logic(initial_state)

    assert "at least one progenitor response" in str(exc_info.value).lower()


def test_tiered_synthesizer_creates_proper_message(tiered_synthesizer):
    """Tests that TieredSynthesizer creates AIMessage with status information."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "Alpha: " + ("x" * 100),
            "bravo_response.md": "Bravo: " + ("y" * 150)
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Should return exactly one message
    assert len(result_state["messages"]) == 1
    ai_message = result_state["messages"][0]

    # Should be an AIMessage
    assert isinstance(ai_message, AIMessage)

    # Should have the specialist name
    assert ai_message.name == "tiered_synthesizer_specialist"

    # Should contain status information about combining
    assert "Alpha" in ai_message.content and "Bravo" in ai_message.content


def test_tiered_synthesizer_handles_empty_string_responses(tiered_synthesizer):
    """Tests edge case where responses are empty strings (not None)."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "",
            "bravo_response.md": "Bravo has content"
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Empty string should be treated as "missing"
    # Should use only Bravo (non-empty response)
    assert result_state["artifacts"]["response_mode"] == "tiered_bravo_only"
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]
    assert "Bravo has content" in combined_response


def test_tiered_synthesizer_preserves_markdown_formatting(tiered_synthesizer):
    """Tests that TieredSynthesizer preserves markdown formatting in responses."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "# Analytical\n\n**Bold** and *italic*",
            "bravo_response.md": "## Contextual\n\n- Bullet 1\n- Bullet 2"
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]

    # Markdown should be preserved
    assert "**Bold**" in combined_response
    assert "*italic*" in combined_response
    assert "- Bullet" in combined_response


def test_tiered_synthesizer_response_format_structure(tiered_synthesizer):
    """Tests that the formatted response has proper structure."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "Alpha content",
            "bravo_response.md": "Bravo content"
        },
        "messages": []
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]

    # Should have markdown heading
    assert combined_response.startswith("#")

    # Should have section separators
    assert "---" in combined_response

    # Should have footer note about multi-perspective
    assert "comprehensive" in combined_response.lower() or "perspective" in combined_response.lower()


def test_tiered_synthesizer_does_not_add_to_user_response_snippets_if_already_present(tiered_synthesizer):
    """Tests that TieredSynthesizer replaces (not appends to) user_response_snippets."""
    # Arrange
    initial_state = {
        "artifacts": {
            "alpha_response.md": "Alpha content",
            "bravo_response.md": "Bravo content"
        },
        "messages": [],
        "scratchpad": {
            "user_response_snippets": ["Old snippet that should be replaced"]
        }
    }

    # Act
    result_state = tiered_synthesizer._execute_logic(initial_state)

    # Assert
    # Should have exactly one snippet (the new combined response)
    assert len(result_state["scratchpad"]["user_response_snippets"]) == 1

    # Should NOT contain the old snippet
    combined_response = result_state["scratchpad"]["user_response_snippets"][0]
    assert "Old snippet" not in combined_response


def test_tiered_synthesizer_full_synthesis(tiered_synthesizer):
    """Tests synthesis when both Alpha and Bravo responses are present."""
    state = create_test_state(
        artifacts={
            "alpha_response.md": "Alpha content",
            "bravo_response.md": "Bravo content"
        }
    )
    
    result = tiered_synthesizer._execute_logic(state)
    
    assert result["task_is_complete"] is True
    assert result["artifacts"]["response_mode"] == "tiered_full"
    
    final_response = result["artifacts"]["final_user_response.md"]
    assert "## Perspective 1: Analytical View" in final_response
    assert "Alpha content" in final_response
    assert "## Perspective 2: Contextual View" in final_response
    assert "Bravo content" in final_response


def test_tiered_synthesizer_graceful_degradation_alpha_only(tiered_synthesizer):
    """Tests synthesis when Bravo is missing."""
    state = create_test_state(
        artifacts={
            "alpha_response.md": "Alpha content"
            # Bravo missing
        }
    )
    
    result = tiered_synthesizer._execute_logic(state)
    
    assert result["artifacts"]["response_mode"] == "tiered_alpha_only"
    final_response = result["artifacts"]["final_user_response.md"]
    assert "# Single-Perspective Response" in final_response
    assert "## Analytical View" in final_response
    assert "Alpha content" in final_response
    assert "Note: This response provides a single perspective" in final_response


def test_tiered_synthesizer_graceful_degradation_bravo_only(tiered_synthesizer):
    """Tests synthesis when Alpha is missing."""
    state = create_test_state(
        artifacts={
            "bravo_response.md": "Bravo content"
            # Alpha missing
        }
    )
    
    result = tiered_synthesizer._execute_logic(state)
    
    assert result["artifacts"]["response_mode"] == "tiered_bravo_only"
    final_response = result["artifacts"]["final_user_response.md"]
    assert "# Single-Perspective Response" in final_response
    assert "## Contextual View" in final_response
    assert "Bravo content" in final_response


def test_tiered_synthesizer_failure_both_missing(tiered_synthesizer):
    """Tests failure when both are missing."""
    state = create_test_state(artifacts={})
    
    with pytest.raises(ValueError, match="requires at least one progenitor response"):
        tiered_synthesizer._execute_logic(state)
