"""Tests for OpenAI response formatter (ADR-UI-003)."""
import pytest
from app.src.interface.openai_schema import ChatCompletionRequest, ChatMessage
from app.src.interface.openai_response_formatter import format_sync_response


def _make_request(model="las-default"):
    return ChatCompletionRequest(
        model=model,
        messages=[ChatMessage(role="user", content="test")],
    )


class TestSyncResponseFormatting:
    def test_basic_response_with_artifact(self):
        final_state = {
            "artifacts": {"final_user_response.md": "The capital of France is Paris."},
            "scratchpad": {},
            "messages": [],
        }
        resp = format_sync_response(final_state, _make_request(), run_id="abc123def456")
        assert resp.object == "chat.completion"
        assert resp.model == "las-default"
        assert len(resp.choices) == 1
        assert resp.choices[0].message.content == "The capital of France is Paris."
        assert resp.choices[0].message.role == "assistant"
        assert resp.choices[0].finish_reason == "stop"
        assert resp.id == "chatcmpl-abc123def456"

    def test_no_artifact_falls_back_to_message(self):
        final_state = {
            "artifacts": {},
            "scratchpad": {},
            "messages": [
                {"type": "ai", "content": "Here is my response."},
            ],
        }
        resp = format_sync_response(final_state, _make_request())
        assert resp.choices[0].message.content == "Here is my response."

    def test_empty_state(self):
        final_state = {
            "artifacts": {},
            "scratchpad": {},
            "messages": [],
        }
        resp = format_sync_response(final_state, _make_request())
        assert resp.choices[0].message.content == ""
        assert resp.choices[0].finish_reason == "stop"

    def test_model_passed_through(self):
        resp = format_sync_response(
            {"artifacts": {"final_user_response.md": "test"}, "scratchpad": {}, "messages": []},
            _make_request(model="las-research"),
        )
        assert resp.model == "las-research"

    def test_response_has_usage(self):
        resp = format_sync_response(
            {"artifacts": {"final_user_response.md": "test"}, "scratchpad": {}, "messages": []},
            _make_request(),
        )
        assert resp.usage is not None
        assert resp.usage.prompt_tokens == 0  # Not implemented yet


class TestInterruptDegradation:
    def test_interrupt_as_regular_content(self):
        final_state = {
            "artifacts": {},
            "scratchpad": {
                "interrupt_data": {
                    "question": "What file format do you want?",
                }
            },
            "messages": [],
        }
        resp = format_sync_response(final_state, _make_request())
        assert "I need more information" in resp.choices[0].message.content
        assert "What file format" in resp.choices[0].message.content
        assert resp.choices[0].finish_reason == "stop"


class TestErrorHandling:
    def test_error_in_scratchpad(self):
        final_state = {
            "artifacts": {},
            "scratchpad": {"error_report": "Something went wrong"},
            "messages": [],
        }
        resp = format_sync_response(final_state, _make_request())
        assert resp.choices[0].finish_reason == "stop"


class TestNoVendorExtensions:
    def test_response_clean(self):
        resp = format_sync_response(
            {"artifacts": {"final_user_response.md": "test"}, "scratchpad": {}, "messages": []},
            _make_request(),
        )
        data = resp.model_dump()
        assert "las_metadata" not in data
        assert "routing_history" not in data
        assert "specialist_count" not in data
