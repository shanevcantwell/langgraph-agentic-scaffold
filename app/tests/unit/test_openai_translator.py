"""Tests for OpenAI streaming translator (ADR-UI-003).

Validates:
- Thought Stream data appears in reasoning_content deltas (per-node)
- final_user_response.md appears in content delta (once)
- No vendor extensions (las_metadata etc.) on chunks
- Null fields excluded from serialization (exclude_none)
- Interrupt and error graceful degradation
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


def _reasoning_chunks(results):
    """Extract chunks that carry reasoning_content."""
    return [r for r in results if isinstance(r, dict)
            and r["choices"][0]["delta"].get("reasoning_content")]


def _content_chunks(results):
    """Extract chunks that carry content."""
    return [r for r in results if isinstance(r, dict)
            and r["choices"][0]["delta"].get("content")]


class TestReasoningContent:
    """Verify Thought Stream data flows through reasoning_content deltas."""

    @pytest.mark.asyncio
    async def test_scratchpad_reasoning_in_reasoning_content(self):
        """Scratchpad *_reasoning and *_decision keys appear in reasoning_content."""
        stream = _mock_stream(
            {"run_id": "test-123"},
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

        rc = _reasoning_chunks(results)
        # At least: workflow start, router node, end node, workflow end
        assert len(rc) >= 3

        # Router reasoning appears in one of the reasoning chunks
        all_reasoning = " ".join(r["choices"][0]["delta"]["reasoning_content"] for r in rc)
        assert "router_reasoning" not in all_reasoning  # Raw key should NOT appear
        assert "The user wants analysis" in all_reasoning  # Content should appear
        assert "[ROUTE] project_director" in all_reasoning
        assert "[TRIAGE] Recommending: project_director" in all_reasoning
        assert "[THINK] ROUTER: The user wants analysis" in all_reasoning

    @pytest.mark.asyncio
    async def test_no_reasoning_after_content(self):
        """Post-content nodes (end_specialist, archiver) must not emit reasoning."""
        stream = _mock_stream(
            {"run_id": "test-leak"},
            {"router_specialist": {
                "scratchpad": {"router_reasoning": "Routing..."},
            }},
            {"project_director": {
                "scratchpad": {"pd_reasoning": "Working..."},
                "artifacts": {"final_user_response.md": "Here is the answer."},
            }},
            # end_specialist fires AFTER content — its reasoning must be suppressed
            {"end_specialist": {
                "scratchpad": {},
                "artifacts": {"archive_report.md": "# Report..."},
            }},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        rc = _reasoning_chunks(results)
        all_reasoning = " ".join(r["choices"][0]["delta"]["reasoning_content"] for r in rc)
        # end_specialist must not appear in reasoning
        assert "end_specialist" not in all_reasoning
        assert "archive_report" not in all_reasoning
        # Think block must be closed before content
        assert "</think>" in all_reasoning

        # Content must not contain any reasoning markers
        cc = _content_chunks(results)
        assert len(cc) == 1
        content = cc[0]["choices"][0]["delta"]["content"]
        assert "[SYS]" not in content
        assert "Workflow complete" not in content

    @pytest.mark.asyncio
    async def test_reasoning_not_in_content(self):
        """Reasoning data must not leak into the content delta."""
        stream = _mock_stream(
            {"run_id": "test-456"},
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

        cc = _content_chunks(results)
        assert len(cc) == 1
        assert cc[0]["choices"][0]["delta"]["content"] == "Here is the answer."
        # Content must not contain reasoning
        assert "Routing to PD" not in cc[0]["choices"][0]["delta"]["content"]

    @pytest.mark.asyncio
    async def test_think_tags_and_workflow_markers(self):
        """Reasoning is wrapped in <think></think> with workflow start/end markers."""
        stream = _mock_stream(
            {"run_id": "test-markers"},
            {"specialist": {"scratchpad": {}, "artifacts": {}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        rc = _reasoning_chunks(results)
        all_reasoning = " ".join(r["choices"][0]["delta"]["reasoning_content"] for r in rc)
        assert "<think>" in all_reasoning
        assert "</think>" in all_reasoning
        assert "[SYS] Workflow initiated" in all_reasoning
        assert "[SYS] Workflow complete" in all_reasoning

    @pytest.mark.asyncio
    async def test_artifacts_key_only_in_reasoning(self):
        """Non-content artifacts appear as key notifications only (no content fencing)."""
        stream = _mock_stream(
            {"run_id": "test-fence"},
            {"pd": {
                "scratchpad": {},
                "artifacts": {
                    "html_document.html": "<html><body>Hello</body></html>",
                    "final_user_response.md": "See the HTML.",
                },
            }},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        rc = _reasoning_chunks(results)
        all_reasoning = "\n".join(r["choices"][0]["delta"]["reasoning_content"] for r in rc)
        assert "[ARTIFACT] html_document.html" in all_reasoning
        # Content must NOT be fenced in reasoning (lives in archive/web-ui)
        assert "<html><body>Hello</body></html>" not in all_reasoning
        assert "```html" not in all_reasoning

    @pytest.mark.asyncio
    async def test_facilitator_complete_in_reasoning(self):
        """facilitator_complete flag produces [OK] entry in reasoning_content."""
        stream = _mock_stream(
            {"run_id": "test-fac"},
            {"facilitator": {
                "scratchpad": {"facilitator_complete": True},
                "artifacts": {},
            }},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        rc = _reasoning_chunks(results)
        all_reasoning = " ".join(r["choices"][0]["delta"]["reasoning_content"] for r in rc)
        assert "[OK] FACILITATOR: Context gathering complete" in all_reasoning


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

        cc = _content_chunks(results)
        assert len(cc) == 1
        assert cc[0]["choices"][0]["delta"]["content"] == "The answer is 42."

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

        cc = _content_chunks(results)
        assert len(cc) == 1
        assert cc[0]["choices"][0]["delta"]["content"] == "First version."

    @pytest.mark.asyncio
    async def test_no_content_run(self):
        """Runs that produce no final_user_response.md still complete cleanly."""
        stream = _mock_stream(
            {"run_id": "test-empty"},
            {"router": {"scratchpad": {}, "artifacts": {}}},
        )

        translator = OpenAiTranslator()
        results = await _collect_output(translator, stream)

        finish_chunks = [r for r in results if isinstance(r, dict)
                        and r["choices"][0].get("finish_reason") == "stop"]
        assert len(finish_chunks) == 1
        assert results[-1] == "[DONE]"


class TestExcludeNone:
    """Verify null fields are excluded from serialized output."""

    @pytest.mark.asyncio
    async def test_no_null_fields_in_sse(self):
        """Chunks must not contain null-valued fields (exclude_none)."""
        stream = _mock_stream(
            {"run_id": "test-none"},
            {"specialist": {"scratchpad": {}, "artifacts": {}}},
        )

        translator = OpenAiTranslator()
        lines = []
        async for line in translator.translate(stream):
            lines.append(line)

        for line in lines:
            if line.startswith("data: ") and not line.startswith("data: [DONE]"):
                parsed = json.loads(line[6:])
                serialized = json.dumps(parsed)
                # No "null" values should appear
                assert ': null' not in serialized


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
        assert len(ids) == 1
        assert models == {"las-research"}

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

        cc = _content_chunks(results)
        assert len(cc) == 1
        assert "What format?" in cc[0]["choices"][0]["delta"]["content"]
        assert "I need more information" in cc[0]["choices"][0]["delta"]["content"]

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

        cc = _content_chunks(results)
        assert len(cc) == 1
        assert "Something went wrong" in cc[0]["choices"][0]["delta"]["content"]
        assert results[-1] == "[DONE]"
