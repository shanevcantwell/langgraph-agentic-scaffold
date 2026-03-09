"""Tests for OpenAI request adapter (ADR-UI-003)."""
import pytest
from app.src.interface.openai_schema import ChatCompletionRequest, ChatMessage
from app.src.interface.openai_request_adapter import translate_request


class TestBasicTranslation:
    def test_single_user_message(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="What is the capital of France?")]
        )
        result = translate_request(req)
        assert result["goal"] == "What is the capital of France?"
        assert result["prior_messages"] is None
        assert result["text_to_process"] is None
        assert result["image_to_process"] is None

    def test_multi_turn_conversation(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(role="user", content="first question"),
                ChatMessage(role="assistant", content="first answer"),
                ChatMessage(role="user", content="follow up question"),
            ]
        )
        result = translate_request(req)
        assert result["goal"] == "follow up question"
        assert result["prior_messages"] is not None
        assert len(result["prior_messages"]) == 2
        assert result["prior_messages"][0]["role"] == "user"
        assert result["prior_messages"][0]["content"] == "first question"
        assert result["prior_messages"][1]["role"] == "assistant"
        assert result["prior_messages"][1]["content"] == "first answer"

    def test_system_messages_excluded_from_prior(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="first question"),
                ChatMessage(role="assistant", content="first answer"),
                ChatMessage(role="user", content="follow up"),
            ]
        )
        result = translate_request(req)
        assert result["goal"] == "follow up"
        # System message should be excluded from prior_messages
        assert len(result["prior_messages"]) == 2
        assert all(m["role"] != "system" for m in result["prior_messages"])


class TestModelMapping:
    def test_default_model(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="test")]
        )
        result = translate_request(req)
        assert result["use_simple_chat"] is False

    def test_simple_model(self):
        req = ChatCompletionRequest(
            model="las-simple",
            messages=[ChatMessage(role="user", content="test")],
        )
        result = translate_request(req)
        assert result["use_simple_chat"] is True

    def test_custom_model(self):
        req = ChatCompletionRequest(
            model="las-research",
            messages=[ChatMessage(role="user", content="test")],
        )
        result = translate_request(req)
        assert result["use_simple_chat"] is False


class TestMultimodalContent:
    def test_text_and_image(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What is this image?"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                    ],
                )
            ]
        )
        result = translate_request(req)
        assert result["goal"] == "What is this image?"
        assert result["image_to_process"] == "data:image/png;base64,abc123"

    def test_multiple_text_parts(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Analyze this document"},
                        {"type": "text", "text": "Here is the document content..."},
                    ],
                )
            ]
        )
        result = translate_request(req)
        assert result["goal"] == "Analyze this document"
        assert result["text_to_process"] == "Here is the document content..."

    def test_non_data_url_ignored(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
                    ],
                )
            ]
        )
        result = translate_request(req)
        # Non-data URLs are not base64 — image_to_process should be None
        assert result["image_to_process"] is None


class TestConversationId:
    def test_conversation_id_passed_through(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="test")],
            conversation_id="conv-abc-123",
        )
        result = translate_request(req)
        assert result["conversation_id"] == "conv-abc-123"

    def test_no_conversation_id(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="test")]
        )
        result = translate_request(req)
        assert result["conversation_id"] is None


class TestEdgeCases:
    def test_empty_messages(self):
        req = ChatCompletionRequest(messages=[])
        result = translate_request(req)
        assert result["goal"] == ""

    def test_only_assistant_messages(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="assistant", content="I said this")]
        )
        result = translate_request(req)
        # No user message — falls back to last message content
        assert result["goal"] == "I said this"

    def test_single_user_no_prior(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")]
        )
        result = translate_request(req)
        assert result["prior_messages"] is None
