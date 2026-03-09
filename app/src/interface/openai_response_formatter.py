"""
Formats WorkflowRunner final state as OpenAI ChatCompletionResponse.

Part of the Two-Headed Architecture (ADR-UI-003).
Used for non-streaming (stream: false) responses.
"""
import time
import uuid
from typing import Dict, Any
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
