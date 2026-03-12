"""
OpenAI streaming translator for the Two-Headed Architecture (ADR-UI-003).

Consumes the same WorkflowRunner.run_streaming() events as AgUiTranslator
and emits spec-compliant ChatCompletionChunk SSE:

    1. Thought Stream data → delta.reasoning_content  (per-node, as specialists execute)
    2. final_user_response.md → delta.content           (once, when produced)
    3. Run completes → finish_reason: "stop"

The reasoning_content field follows the convention established by DeepSeek R1
and adopted by Qwen, LM Studio, and most OpenAI-compatible clients. Clients
that don't understand reasoning_content simply ignore it (field omitted when
null via exclude_none serialization).

For interrupts (clarification needed), the questions are emitted as regular
content with finish_reason: "stop" (graceful degradation for standard clients).
"""
import logging
import time
import uuid
from typing import AsyncGenerator, Dict, Any, List

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
                # Workflow start marker — open <think> for clients that
                # use tag-based reasoning detection (AnythingLLM, etc.)
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(reasoning_content="<think>\n[SYS] Workflow initiated\n"),
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

            # Process node outputs
            for node_name, node_output in chunk.items():
                if not isinstance(node_output, dict):
                    continue

                # --- Reasoning: extract Thought Stream for this node ---
                # Stop emitting reasoning once content has been sent — late
                # reasoning (end_specialist, archiver) would leak into the
                # client's content display on clients that don't separate them.
                if not self._content_emitted:
                    reasoning_text = self._extract_node_reasoning(node_name, node_output)
                    if reasoning_text:
                        yield self._format_sse(self._make_chunk(
                            delta=DeltaContent(reasoning_content=reasoning_text),
                        ))

                # --- Content: accumulate artifacts, emit final_user_response.md ---
                node_artifacts = node_output.get("artifacts", {})
                if isinstance(node_artifacts, dict):
                    self._accumulated_artifacts.update(node_artifacts)

                content = node_artifacts.get("final_user_response.md", "")
                if content and not self._content_emitted:
                    # Close thinking block before content
                    yield self._format_sse(self._make_chunk(
                        delta=DeltaContent(reasoning_content="[SYS] Workflow complete\n</think>"),
                    ))
                    yield self._format_sse(self._make_chunk(
                        delta=DeltaContent(content=content),
                    ))
                    self._content_emitted = True

        # Stream complete — check accumulated artifacts for late content
        if not self._content_emitted:
            final_content = self._accumulated_artifacts.get("final_user_response.md", "")
            if final_content:
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(reasoning_content="[SYS] Workflow complete\n</think>"),
                ))
                yield self._format_sse(self._make_chunk(
                    delta=DeltaContent(content=final_content),
                ))
                self._content_emitted = True

        # If no content was ever produced, close the think block
        if not self._content_emitted:
            yield self._format_sse(self._make_chunk(
                delta=DeltaContent(reasoning_content="[SYS] Workflow complete\n</think>"),
            ))

        yield self._format_sse(self._make_chunk(finish_reason="stop"))
        yield "data: [DONE]\n\n"

    def _extract_node_reasoning(self, node_name: str, node_output: Dict[str, Any]) -> str:
        """
        Extract Thought Stream entries from a node output, mirroring the
        web-ui's handleStreamEvent → addThoughtStreamEntry pipeline.

        Returns a reasoning text block for this node, or empty string if nothing to emit.
        """
        parts: List[str] = []

        # Lifecycle start
        parts.append(f"[SYS] {node_name} starting...")

        # Scratchpad reasoning
        scratchpad = node_output.get("scratchpad", {})
        if isinstance(scratchpad, dict):
            # Triage recommendations
            recs = scratchpad.get("recommended_specialists", [])
            if isinstance(recs, list) and recs:
                parts.append(f"[TRIAGE] Recommending: {', '.join(recs)}")

            # Router decision
            if "router_decision" in scratchpad:
                parts.append(f"[ROUTE] {scratchpad['router_decision']}")

            # Generic *_reasoning and *_decision keys
            for key, val in scratchpad.items():
                if key.endswith("_reasoning"):
                    label = key.replace("_reasoning", "").upper().replace("_", " ")
                    parts.append(f"[THINK] {label}: {val}")
                elif key.endswith("_decision") and key != "router_decision":
                    label = key.replace("_decision", "").upper().replace("_", " ")
                    parts.append(f"[{label}] {val}")

            # Facilitator complete flag
            if scratchpad.get("facilitator_complete"):
                parts.append("[OK] FACILITATOR: Context gathering complete")

        # Artifacts — key notification only (content lives in archive/web-ui)
        node_artifacts = node_output.get("artifacts", {})
        if isinstance(node_artifacts, dict):
            for art_key in node_artifacts:
                if art_key == "final_user_response.md":
                    continue
                parts.append(f"[ARTIFACT] {art_key}")

        # Errors
        if "error" in node_output:
            parts.append(f"[ERROR] {node_name}: {node_output['error']}")

        # Lifecycle complete
        parts.append(f"[OK] {node_name} complete")

        return "\n\n".join(parts) + "\n\n"

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
        """Format a chunk as an SSE data line, excluding null fields."""
        return f"data: {chunk.model_dump_json(exclude_none=True)}\n\n"

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
