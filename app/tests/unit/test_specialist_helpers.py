# app/tests/unit/test_specialist_helpers.py
"""
Tests for specialist helper functions.

Includes tests for the "not me" pattern (create_decline_response).
"""
import pytest
from langchain_core.messages import AIMessage

from app.src.specialists.helpers import (
    create_llm_message,
    create_error_message,
    create_decline_response,
)


class TestCreateDeclineResponse:
    """Tests for the 'not me' pattern helper function."""

    def test_decline_response_basic(self):
        """Test basic decline response structure."""
        result = create_decline_response(
            specialist_name="text_analysis_specialist",
            reason="Missing required artifact",
        )

        # Check message
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert "text_analysis_specialist" in result["messages"][0].content
        assert "Missing required artifact" in result["messages"][0].content
        assert result["messages"][0].additional_kwargs.get("is_decline") is True

        # Check scratchpad
        assert "scratchpad" in result
        assert result["scratchpad"]["decline_task"] is True
        assert result["scratchpad"]["decline_reason"] == "Missing required artifact"
        assert result["scratchpad"]["declining_specialist"] == "text_analysis_specialist"

    def test_decline_response_with_recommendations(self):
        """Test decline response with alternative specialist recommendations."""
        result = create_decline_response(
            specialist_name="vision_specialist",
            reason="Image is corrupted",
            recommended_specialists=["chat_specialist", "default_responder_specialist"],
        )

        # Check recommendations are included
        assert result["scratchpad"]["recommended_specialists"] == [
            "chat_specialist",
            "default_responder_specialist",
        ]

    def test_decline_response_message_format(self):
        """Test that decline message follows expected format for UI display."""
        result = create_decline_response(
            specialist_name="researcher_specialist",
            reason="Search API unavailable",
        )

        message = result["messages"][0]
        # Should be formatted for clear display
        assert message.content == "[researcher_specialist] I cannot handle this task: Search API unavailable"
        assert message.name == "researcher_specialist"


class TestCreateErrorMessage:
    """Tests for error message helper."""

    def test_error_message_basic(self):
        """Test basic error message structure."""
        result = create_error_message("Something went wrong")

        assert "messages" in result
        assert result["messages"][0].additional_kwargs.get("is_error") is True
        assert "Something went wrong" in result["messages"][0].content

    def test_error_message_with_recommendations(self):
        """Test error message with specialist recommendations."""
        result = create_error_message(
            "Failed to process",
            recommended_specialists=["fallback_specialist"],
        )

        assert result["scratchpad"]["recommended_specialists"] == ["fallback_specialist"]


class TestCreateLlmMessage:
    """Tests for LLM message helper."""

    def test_llm_message_with_adapter(self):
        """Test message creation with adapter."""
        from unittest.mock import MagicMock

        mock_adapter = MagicMock()
        mock_adapter.model_name = "test-model-v1"

        result = create_llm_message(
            specialist_name="test_specialist",
            llm_adapter=mock_adapter,
            content="Test content",
        )

        assert result.content == "Test content"
        assert result.name == "test_specialist"
        assert result.additional_kwargs["llm_name"] == "test-model-v1"

    def test_llm_message_without_adapter(self):
        """Test message creation without adapter defaults to unknown_model."""
        result = create_llm_message(
            specialist_name="test_specialist",
            llm_adapter=None,
            content="Test content",
        )

        assert result.additional_kwargs["llm_name"] == "unknown_model"
