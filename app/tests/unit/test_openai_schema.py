"""Tests for OpenAI-compatible schema models (ADR-UI-003)."""
import pytest
from app.src.interface.openai_schema import (
    ChatCompletionRequest,
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    DeltaContent,
    UsageInfo,
)


class TestChatCompletionRequest:
    def test_minimal_request(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hello")]
        )
        assert req.model == "las-default"
        assert req.stream is False
        assert len(req.messages) == 1
        assert req.messages[0].role == "user"
        assert req.messages[0].content == "hello"

    def test_streaming_request(self):
        req = ChatCompletionRequest(
            model="las-simple",
            messages=[ChatMessage(role="user", content="test")],
            stream=True,
        )
        assert req.model == "las-simple"
        assert req.stream is True

    def test_multimodal_content(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "What is this?"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}},
                    ],
                )
            ]
        )
        assert isinstance(req.messages[0].content, list)
        assert len(req.messages[0].content) == 2

    def test_conversation_id(self):
        req = ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="hi")],
            conversation_id="conv-123",
        )
        assert req.conversation_id == "conv-123"

    def test_multi_turn_messages(self):
        req = ChatCompletionRequest(
            messages=[
                ChatMessage(role="user", content="first question"),
                ChatMessage(role="assistant", content="first answer"),
                ChatMessage(role="user", content="follow up"),
            ]
        )
        assert len(req.messages) == 3
        assert req.messages[2].content == "follow up"


class TestChatCompletionResponse:
    def test_response_structure(self):
        resp = ChatCompletionResponse(
            model="las-default",
            choices=[
                ChatCompletionChoice(
                    message=ChatCompletionMessage(content="Hello!"),
                    finish_reason="stop",
                )
            ],
        )
        assert resp.object == "chat.completion"
        assert resp.model == "las-default"
        assert len(resp.choices) == 1
        assert resp.choices[0].message.content == "Hello!"
        assert resp.choices[0].message.role == "assistant"
        assert resp.choices[0].finish_reason == "stop"

    def test_response_has_id_and_created(self):
        resp = ChatCompletionResponse(
            choices=[ChatCompletionChoice(message=ChatCompletionMessage(content="test"))]
        )
        assert resp.id.startswith("chatcmpl-")
        assert resp.created > 0

    def test_response_serialization(self):
        resp = ChatCompletionResponse(
            choices=[ChatCompletionChoice(message=ChatCompletionMessage(content="test"))]
        )
        data = resp.model_dump()
        assert data["object"] == "chat.completion"
        assert "choices" in data
        assert data["choices"][0]["message"]["role"] == "assistant"


class TestChatCompletionChunk:
    def test_chunk_structure(self):
        chunk = ChatCompletionChunk(
            model="las-default",
            choices=[
                ChatCompletionChunkChoice(
                    delta=DeltaContent(content="Hello"),
                )
            ],
        )
        assert chunk.object == "chat.completion.chunk"
        assert chunk.choices[0].delta.content == "Hello"
        assert chunk.choices[0].finish_reason is None

    def test_finish_chunk(self):
        chunk = ChatCompletionChunk(
            choices=[
                ChatCompletionChunkChoice(
                    delta=DeltaContent(),
                    finish_reason="stop",
                )
            ],
        )
        assert chunk.choices[0].finish_reason == "stop"
        assert chunk.choices[0].delta.content is None

    def test_role_chunk(self):
        chunk = ChatCompletionChunk(
            choices=[
                ChatCompletionChunkChoice(
                    delta=DeltaContent(role="assistant"),
                )
            ],
        )
        assert chunk.choices[0].delta.role == "assistant"

    def test_chunk_json_serialization(self):
        chunk = ChatCompletionChunk(
            model="las-default",
            choices=[
                ChatCompletionChunkChoice(delta=DeltaContent(content="test"))
            ],
        )
        json_str = chunk.model_dump_json()
        assert '"chat.completion.chunk"' in json_str
        assert '"test"' in json_str


class TestNoVendorExtensions:
    """Verify that no las_metadata or vendor-specific fields exist on any model."""

    def test_response_no_las_metadata(self):
        resp = ChatCompletionResponse(
            choices=[ChatCompletionChoice(message=ChatCompletionMessage(content="test"))]
        )
        data = resp.model_dump()
        assert "las_metadata" not in data
        assert "metadata" not in data

    def test_chunk_no_las_metadata(self):
        chunk = ChatCompletionChunk(
            choices=[ChatCompletionChunkChoice(delta=DeltaContent(content="test"))]
        )
        data = chunk.model_dump()
        assert "las_metadata" not in data
        assert "metadata" not in data
