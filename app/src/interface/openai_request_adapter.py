"""
Translates OpenAI ChatCompletionRequest into WorkflowRunner kwargs.

Part of the Two-Headed Architecture (ADR-UI-003).
Maps standard OpenAI message format to LAS's internal invocation contract.
"""
import logging
from typing import Dict, Any, Optional
from .openai_schema import ChatCompletionRequest

logger = logging.getLogger(__name__)


def translate_request(request: ChatCompletionRequest) -> Dict[str, Any]:
    """
    Convert a ChatCompletionRequest into kwargs for WorkflowRunner.run() or run_streaming().

    Mapping:
        messages[-1] where role=="user" → goal
        messages[:-1] → prior_messages (already [{role, content}])
        multimodal content parts → image_to_process, text_to_process
        model name → use_simple_chat flag (for now)
        conversation_id → conversation_id

    Returns:
        Dict with keys matching WorkflowRunner.run_streaming() parameters:
            goal, text_to_process, image_to_process, use_simple_chat,
            conversation_id, prior_messages
    """
    # Extract the last user message as the goal
    goal = ""
    text_to_process = None
    image_to_process = None

    # Find the last user message
    last_user_idx = None
    for i in range(len(request.messages) - 1, -1, -1):
        if request.messages[i].role == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        # No user message found — use last message content as goal
        if request.messages:
            goal = _extract_text_content(request.messages[-1].content)
        else:
            goal = ""
    else:
        user_msg = request.messages[last_user_idx]
        content = user_msg.content

        if isinstance(content, str):
            goal = content
        elif isinstance(content, list):
            # Multimodal: extract text and image parts
            goal, text_to_process, image_to_process = _extract_multimodal_parts(content)

    # Build prior_messages from all messages before the last user message
    prior_messages = None
    if last_user_idx is not None and last_user_idx > 0:
        prior_messages = []
        for msg in request.messages[:last_user_idx]:
            # Skip system messages — LAS doesn't use them in prior_messages
            if msg.role == "system":
                continue
            prior_messages.append({
                "role": msg.role,
                "content": _extract_text_content(msg.content),
            })

    # Model name → routing flags
    use_simple_chat = _model_to_simple_chat(request.model)

    return {
        "goal": goal,
        "text_to_process": text_to_process,
        "image_to_process": image_to_process,
        "use_simple_chat": use_simple_chat,
        "conversation_id": request.conversation_id,
        "prior_messages": prior_messages,
    }


def _extract_text_content(content) -> str:
    """Extract text from content that may be string or list of content parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return "\n".join(text_parts) if text_parts else ""
    return str(content)


def _extract_multimodal_parts(content_parts: list) -> tuple:
    """
    Extract text goal, text_to_process, and image_to_process from multimodal content parts.

    Returns:
        (goal, text_to_process, image_to_process)
    """
    text_parts = []
    image_data = None

    for part in content_parts:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type", "")
        if part_type == "text":
            text_parts.append(part.get("text", ""))
        elif part_type == "image_url":
            image_url = part.get("image_url", {})
            url = image_url.get("url", "") if isinstance(image_url, dict) else str(image_url)
            # base64 data URLs go directly to image_to_process
            if url.startswith("data:"):
                image_data = url

    goal = text_parts[0] if text_parts else ""
    # If there are multiple text parts, the rest become text_to_process
    text_to_process = "\n".join(text_parts[1:]) if len(text_parts) > 1 else None

    return goal, text_to_process, image_data


def _model_to_simple_chat(model: str) -> bool:
    """
    Map model name to use_simple_chat flag.

    For now, 'las-simple' triggers simple chat mode.
    All other profiles use the default tiered chat.
    """
    return model == "las-simple"
