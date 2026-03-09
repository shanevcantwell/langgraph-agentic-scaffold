"""
OpenAI streaming translator for the Two-Headed Architecture (ADR-UI-003).

THIS IS A FILTER, NOT A MAPPER.

It consumes the same WorkflowRunner.run_streaming() events as AgUiTranslator
but deliberately discards most of them. It only emits ChatCompletionChunk
objects in two cases:

    1. When final_user_response.md appears in artifacts → delta.content
    2. When the run completes → finish_reason: "stop"

Everything else (specialist lifecycle, routing decisions, thoughts, MCP calls,
state snapshots, scratchpad data) is silently dropped. That data is served by
the observability head (/v1/graph/stream/events), not the chat head.

For interrupts (clarification needed), the questions are emitted as regular
content with finish_reason: "stop" (graceful degradation for standard clients).
"""
import json
import logging
import time
import uuid
from typing import AsyncGenerator, Dict, Any

from .openai_schema import ChatCompletionChunk, ChatCompletionChunkChoice, DeltaContent

logger = logging.getLogger(__name__)


class OpenAiTranslator:
    """
    Translates raw LangGraph stream events into OpenAI ChatCompletionChunk SSE format.
    """

    def __init__(self, model: str = "las-default"):
        self.model = model
        self.run_id = None
        self.response_id = None
        self.created = int(time.time())
        self._content_emitted = False
        # Track artifacts across nodes to detect final_user_response.md
        self._accumulated_artifacts = {}

    async def translate(
        self, raw_stream: AsyncGenerator[Dict[str, Any], None]
    ) -> AsyncGenerator[str, None]:
        """
        Consumes the raw stream from WorkflowRunner.run_streaming() and yields
        SSE-formatted strings (data: {...}\n\n) suitable for StreamingResponse.

        Most events are silently discarded. Only content and completion are emitted.
        """
        async for chunk in raw_stream:
            # Capture run_id metadata (emitted first by WorkflowRunner)
            if "run_id" in chunk:
                self.run_id = chunk["run_id"]
                self.response_id = f"chatcmpl-{self.run_id[:12]}"
                # Emit initial chunk with role
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(role="assistant"),
                ))
                continue

            # Skip other metadata chunks (conversation_id, thread_id)
            if "conversation_id" in chunk or "thread_id" in chunk:
                continue

            # Handle interrupt events — degrade gracefully
            if "__interrupt__" in chunk:
                interrupt_content = self._extract_interrupt_content(chunk)
                if interrupt_content:
                    yield self._format_sse(self._make_chunk(
                        delta=DeltaContent(content=interrupt_content),
                    ))
                    self._content_emitted = True
                # Emit stop after interrupt content
                yield self._format_sse(self._make_chunk(
                    finish_reason="stop",
                ))
                yield "data: [DONE]\n\n"
                return

            # Handle error chunks
            if "error" in chunk and not any(k for k in chunk if k not in ("error", "scratchpad", "error_report")):
                error_msg = chunk.get("error", "An error occurred")
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(content=f"Error: {error_msg}"),
                ))
                self._content_emitted = True
                yield self._format_sse(self._make_chunk(finish_reason="stop"))
                yield "data: [DONE]\n\n"
                return

            # Process node outputs — look for final_user_response.md
            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue

                # Accumulate artifacts (dict merge, matching GraphState reducer)
                node_artifacts = node_output.get("artifacts", {})
                if isinstance(node_artifacts, dict):
                    self._accumulated_artifacts.update(node_artifacts)

                # Check if final_user_response.md just appeared
                content = node_artifacts.get("final_user_response.md", "")
                if content and not self._content_emitted:
                    yield self._format_sse(self._make_chunk(
                        delta=DeltaContent(content=content),
                    ))
                    self._content_emitted = True

                # Everything else (scratchpad, state_timeline, routing_history,
                # messages, etc.) is silently dropped. The observability head
                # serves that data.

        # Stream complete — emit finish chunk and DONE sentinel
        # If no content was emitted, check accumulated artifacts
        if not self._content_emitted:
            final_content = self._accumulated_artifacts.get("final_user_response.md", "")
            if final_content:
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(content=final_content),
                ))
                self._content_emitted = True

        yield self._format_sse(self._make_chunk(finish_reason="stop"))
        yield "data: [DONE]\n\n"

    def _make_chunk(
        self,
        delta: DeltaContent = None,
        finish_reason: str = None,
    ) -> ChatCompletionChunk:
        """Build a ChatCompletionChunk with consistent id/model/created."""
        return ChatCompletionChunk(
            id=self.response_id or f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=self.created,
            model=self.model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=delta or DeltaContent(),
                    finish_reason=finish_reason,
                )
            ],
        )

    def _format_sse(self, chunk: ChatCompletionChunk) -> str:
        """Format a chunk as an SSE data line."""
        return f"data: {chunk.model_dump_json()}\n\n"

    def _extract_interrupt_content(self, chunk: Dict[str, Any]) -> str:
        """
        Extract clarification questions from an interrupt event and format
        as regular content (graceful degradation for standard clients).
        """
        interrupt_data = chunk.get("__interrupt__", [])
        if not interrupt_data:
            return ""

        payload = interrupt_data[0]
        value = payload.value if hasattr(payload, "value") else payload.get("value", {})

        if isinstance(value, dict):
            question = value.get("question", "")
            reason = value.get("reason", "")
            if question:
                parts = ["I need more information before proceeding:"]
                if reason:
                    parts.append(f"\n**Reason:** {reason}")
                parts.append(f"\n{question}")
                return "\n".join(parts)

        return f"I need more information before proceeding:\n\n{value}"
