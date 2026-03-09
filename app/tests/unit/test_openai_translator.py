"""Tests for OpenAI streaming translator (ADR-UI-003).

Validates that the translator is a FILTER, not a mapper:
- Most events are silently discarded
- Only final_user_response.md content and run completion are emitted
- No las_metadata or vendor extensions appear on chunks
"""
import pytest
import json
from app.src.interface.openai_translator import OpenAiTranslator


async def _mock_stream(*chunks):
    """Create an async generator from a sequence of chunks."""
    for chunk in chunks:
        yield chunk


def _parse_sse_lines(lines):
    """Parse SSE data lines into a list of dicts (or '[DONE]' strings)."""
    results = []
    for line in lines:
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload == "[DONE]":
                results.append("[DONE]")
            else:
                results.append(json.loads(payload))
    return results


async def _collect_output(translator, stream):
    """Collect all SSE output from the translator."""
    lines = []
    async for line in translator.translate(stream):
        lines.append(line)
    return _parse_sse_lines(lines)


class TestFilterBehavior:
    """Verify the translator discards non-content events."""

    @pytest.mark.asyncio
    async def test_drops_specialist_lifecycle(self):
        """Node start/end events should produce no output (except final content)."""
        stream = _mock_stream(
            {"run_id": "test-123"},
            {"conversation_id": "conv-1"},
            {"router_specialist": {
                "scratchpad": {"router_reasoning": "Routing to PD"},
                "routing_history": ["router_specialist"],
                "messages": [],
            }},
            {"project_director": {
                "scratchpad": {"pd_reasoning": "Executing tools..."},
                "artifacts": {"final_user_response.md": "Here is the answer."},
                "messages": [],
            }},
        )

        translator = OpenAiTranslator(model="las-default")
        results = await _collect_output(translator, stream)

        # Should have: role chunk, content chunk, finish chunk, [DONE]
        assert len(results) == 4
        # First: role
        assert results[0]["choices"][0]["delta"]["role"] == "assistant"
        # Second: content from final_user_response.md
        assert results[1]["choices"][0]["delta"]["content"] == "Here is the answer."
        # Third: finish
        assert results[2]["choices"][0]["finish_reason"] == "stop"
        # Fourth: DONE
        assert results[3] == "[DONE]"

    @pytest.mark.asyncio
    async def test_no_scratchpad_in_output(self):
        """Scratchpad data (thoughts, routing decisions) must not appear in output."""
        stream = _mock_stream(
            {"run_id": "test-456"},
            {"router_specialist": {
                "scratchpad": {
                    "router_reasoning": "The user wants analysis...",
                    "router_decision": "project_director",
                    "recommended_specialists": ["project_director"],
                },
                "artifacts": {},
            }},
            {"end_specialist": {
                "artifacts": {"final_user_response.md": "Done."},
            }},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        # Check no output contains scratchpad data
        for result in results:
            if isinstance(result, dict):
                serialized = json.dumps(result)
                assert "router_reasoning" not in serialized
                assert "router_decision" not in serialized
                assert "recommended_specialists" not in serialized

    @pytest.mark.asyncio
    async def test_no_las_metadata(self):
        """No las_metadata or vendor extensions on any chunk."""
        stream = _mock_stream(
            {"run_id": "test-789"},
            {"specialist": {"artifacts": {"final_user_response.md": "Content."}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        for result in results:
            if isinstance(result, dict):
                assert "las_metadata" not in result
                assert "metadata" not in result
                assert result.get("object") == "chat.completion.chunk"


class TestContentEmission:

    @pytest.mark.asyncio
    async def test_content_from_final_user_response(self):
        """Content is extracted from artifacts['final_user_response.md']."""
        stream = _mock_stream(
            {"run_id": "test-content"},
            {"pd": {"artifacts": {"final_user_response.md": "The answer is 42."}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        content_chunks = [r for r in results if isinstance(r, dict)
                         and r["choices"][0]["delta"].get("content")]
        assert len(content_chunks) == 1
        assert content_chunks[0]["choices"][0]["delta"]["content"] == "The answer is 42."

    @pytest.mark.asyncio
    async def test_content_emitted_only_once(self):
        """If multiple nodes produce final_user_response.md, emit only the first."""
        stream = _mock_stream(
            {"run_id": "test-once"},
            {"pd": {"artifacts": {"final_user_response.md": "First version."}}},
            {"ei": {"artifacts": {"final_user_response.md": "Updated version."}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        content_chunks = [r for r in results if isinstance(r, dict)
                         and r["choices"][0]["delta"].get("content")]
        # Only the first appearance is emitted
        assert len(content_chunks) == 1
        assert content_chunks[0]["choices"][0]["delta"]["content"] == "First version."

    @pytest.mark.asyncio
    async def test_no_content_run(self):
        """Runs that produce no final_user_response.md still complete cleanly."""
        stream = _mock_stream(
            {"run_id": "test-empty"},
            {"router": {"scratchpad": {}, "artifacts": {}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        # Should have: role, finish, DONE (no content chunk)
        finish_chunks = [r for r in results if isinstance(r, dict)
                        and r["choices"][0].get("finish_reason") == "stop"]
        assert len(finish_chunks) == 1
        assert results[-1] == "[DONE]"


class TestSSEFormat:

    @pytest.mark.asyncio
    async def test_sse_line_format(self):
        """Each output line must be 'data: {json}\\n\\n' format."""
        stream = _mock_stream(
            {"run_id": "test-sse"},
            {"pd": {"artifacts": {"final_user_response.md": "test"}}},
        )

        translator = OpenAiTranslator()
        lines = []
        async for line in translator.translate(stream):
            lines.append(line)

        for line in lines:
            assert line.startswith("data: ")
            assert line.endswith("\n\n")

    @pytest.mark.asyncio
    async def test_done_sentinel(self):
        """Stream must end with 'data: [DONE]\\n\\n'."""
        stream = _mock_stream({"run_id": "test-done"})

        translator = OpenAiTranslator()
        lines = []
        async for line in translator.translate(stream):
            lines.append(line)

        assert lines[-1] == "data: [DONE]\n\n"

    @pytest.mark.asyncio
    async def test_consistent_id_and_model(self):
        """All chunks in a stream share the same id and model."""
        stream = _mock_stream(
            {"run_id": "test-consistent"},
            {"pd": {"artifacts": {"final_user_response.md": "content"}}},
        )

        translator = OpenAiTranslator(model="las-research")
        results = await _collect_output(translator, stream)

        chunk_results = [r for r in results if isinstance(r, dict)]
        ids = set(r["id"] for r in chunk_results)
        models = set(r["model"] for r in chunk_results)
        assert len(ids) == 1  # All same id
        assert models == {"las-research"}


class TestInterruptHandling:

    @pytest.mark.asyncio
    async def test_interrupt_degrades_gracefully(self):
        """Interrupt events produce clarification as regular content, then stop."""
        stream = _mock_stream(
            {"run_id": "test-interrupt"},
            {"__interrupt__": [type("Interrupt", (), {"value": {"question": "What format?", "reason": "Need clarification"}})()]},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        # Should have: role, interrupt content, finish, DONE
        content_chunks = [r for r in results if isinstance(r, dict)
                         and r["choices"][0]["delta"].get("content")]
        assert len(content_chunks) == 1
        assert "What format?" in content_chunks[0]["choices"][0]["delta"]["content"]
        assert "I need more information" in content_chunks[0]["choices"][0]["delta"]["content"]

        # Must end with stop
        finish_chunks = [r for r in results if isinstance(r, dict)
                        and r["choices"][0].get("finish_reason") == "stop"]
        assert len(finish_chunks) == 1
        assert results[-1] == "[DONE]"


class TestErrorHandling:

    @pytest.mark.asyncio
    async def test_error_emitted_as_content(self):
        """Error events produce error message as content, then stop."""
        stream = _mock_stream(
            {"run_id": "test-error"},
            {"error": "Something went wrong", "scratchpad": {"error_report": "Details..."}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        content_chunks = [r for r in results if isinstance(r, dict)
                         and r["choices"][0]["delta"].get("content")]
        assert len(content_chunks) == 1
        assert "Something went wrong" in content_chunks[0]["choices"][0]["delta"]["content"]
        assert results[-1] == "[DONE]"
