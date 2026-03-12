"""
Formats WorkflowRunner final state as OpenAI ChatCompletionResponse.

Part of the Two-Headed Architecture (ADR-UI-003).
Used for non-streaming (stream: false) responses.
"""
import time
import uuid
from typing import Dict, Any, List, Optional
from .openai_schema import (
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    UsageInfo,
)


def format_sync_response(
    final_state: Dict[str, Any],
    request: ChatCompletionRequest,
    run_id: str = None,
) -> ChatCompletionResponse:
    """
    Convert WorkflowRunner final state into an OpenAI ChatCompletionResponse.

    Content source: artifacts["final_user_response.md"]
    Finish reason: derived from completion_signal artifact or presence of content.

    For interrupts (clarification needed), the clarification questions are
    returned as regular content with finish_reason="stop" (graceful degradation).
    """
    artifacts = final_state.get("artifacts", {})
    content = artifacts.get("final_user_response.md", "")

    # If no final_user_response, check for interrupt/clarification
    if not content:
        content = _extract_interrupt_content(final_state)

    # If still no content, fall back to last message
    if not content:
        content = _extract_last_message_content(final_state)

    finish_reason = _determine_finish_reason(final_state, content)
    reasoning = _extract_all_reasoning(final_state)

    response_id = f"chatcmpl-{run_id[:12]}" if run_id else f"chatcmpl-{uuid.uuid4().hex[:12]}"

    return ChatCompletionResponse(
        id=response_id,
        created=int(time.time()),
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=content or "",
                    reasoning_content=reasoning,
                ),
                finish_reason=finish_reason,
            )
        ],
        usage=UsageInfo(),  # Token counting not implemented yet
    )


def _extract_interrupt_content(final_state: Dict[str, Any]) -> str:
    """
    If the workflow was interrupted for clarification, format the questions
    as regular content (graceful degradation for standard clients).
    """
    scratchpad = final_state.get("scratchpad", {})
    if not isinstance(scratchpad, dict):
        return ""

    # Check for hitl() interrupt data
    interrupt_data = scratchpad.get("interrupt_data", {})
    if isinstance(interrupt_data, dict):
        question = interrupt_data.get("question", "")
        if question:
            return f"I need more information before proceeding:\n\n{question}"

    return ""


def _extract_last_message_content(final_state: Dict[str, Any]) -> str:
    """Fall back to the last assistant message in the state."""
    messages = final_state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, dict):
            if msg.get("role") == "assistant" or msg.get("type") == "ai":
                return msg.get("content", "")
        elif hasattr(msg, "type") and msg.type == "ai":
            return getattr(msg, "content", "")
    return ""


def _determine_finish_reason(final_state: Dict[str, Any], content: str) -> str:
    """
    Determine the OpenAI finish_reason from the workflow state.

    Always returns "stop" — LAS does not do token-level streaming,
    so "length" (truncation) doesn't apply. Interrupts are degraded
    to regular content with finish_reason="stop".
    """
    # Check for errors
    scratchpad = final_state.get("scratchpad", {})
    if isinstance(scratchpad, dict):
        if scratchpad.get("error_report") or scratchpad.get("error"):
            return "stop"

    return "stop"


def _extract_all_reasoning(final_state: Dict[str, Any]) -> Optional[str]:
    """
    Extract accumulated Thought Stream data from final workflow state.

    Mirrors the streaming translator's per-node extraction but operates on
    the merged final state. Returns None if no reasoning data found.
    """
    parts: List[str] = []

    # Routing history trace
    routing_history = final_state.get("routing_history", [])
    if routing_history:
        route_trace = " → ".join(routing_history)
        parts.append(f"[ROUTE] {route_trace}")

    # Scratchpad reasoning (accumulated across all specialists via dict merge)
    scratchpad = final_state.get("scratchpad", {})
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
    artifacts = final_state.get("artifacts", {})
    if isinstance(artifacts, dict):
        for art_key in artifacts:
            if art_key == "final_user_response.md":
                continue
            parts.append(f"[ARTIFACT] {art_key}")

    return "\n".join(parts) if parts else None
