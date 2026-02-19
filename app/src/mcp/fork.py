"""
fork() — Recursive LAS invocation for context-isolated subtasks.

ADR-CORE-045: LAS as Recursive Tool.

Spawns a fresh LAS instance by calling the graph invoke API. The child
gets its own context window, full tool access, and complete pipeline
(Triage → SA → Router → Specialist). Result comes back as a concise
string; all intermediate context in the child is discarded on return.

Use when processing multiple independent items that each require LLM
reasoning — each fork prevents context accumulation in the parent.
"""
import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)

# Subagent marker prepended to every fork prompt
_SUBAGENT_PREFIX = (
    "[SUBAGENT] You are executing as a focused subagent of a parent workflow. "
    "Complete the specific task below and return a concise result.\n\n"
)

# LAS API endpoint — localhost because fork originates from within
# the same langgraph-app container that serves the API.
_LAS_INVOKE_URL = "http://localhost:8000/v1/graph/invoke"


def dispatch_fork(
    prompt: str,
    context: str | None = None,
    timeout: float = 300.0,
) -> str:
    """
    Spawn a fresh LAS invocation to handle a subtask.

    Args:
        prompt: Task prompt for the child. Written like a task for a
                skilled colleague — say what you need, not how to do it.
        context: Optional document content or context to pass. Only what
                 the subagent needs for this specific subtask.
        timeout: HTTP timeout in seconds (default 300s — child may need
                 multiple react_step iterations).

    Returns:
        Result string from the child invocation, or an error message
        prefixed with "Error:" on failure.
    """
    full_prompt = f"{_SUBAGENT_PREFIX}{prompt}"

    request_body: Dict[str, Any] = {
        "input_prompt": full_prompt,
    }
    if context:
        request_body["text_to_process"] = context

    logger.info(f"fork(): Spawning subagent — prompt length={len(prompt)}, "
                f"context={'yes' if context else 'no'}")

    try:
        response = httpx.post(
            _LAS_INVOKE_URL,
            json=request_body,
            timeout=timeout,
        )
        response.raise_for_status()

        data = response.json()
        return _extract_result(data)

    except httpx.TimeoutException:
        msg = f"Error: fork timed out after {timeout}s"
        logger.error(msg)
        return msg
    except httpx.HTTPStatusError as e:
        msg = f"Error: fork failed with HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(msg)
        return msg
    except Exception as e:
        msg = f"Error: fork failed: {e}"
        logger.error(msg, exc_info=True)
        return msg


def _extract_result(data: Dict[str, Any]) -> str:
    """
    Extract a concise result string from the LAS invoke response.

    Tries: last message content → artifacts summary → error_report.
    """
    final_output = data.get("final_output", {})

    # Check for error_report first
    if isinstance(final_output, dict) and "error_report" in final_output:
        return f"Error: subagent error — {final_output['error_report']}"

    # Extract last message content (the specialist's output)
    messages = final_output.get("messages", [])
    if messages:
        last_msg = messages[-1]
        # Messages may be dicts or LangChain message objects serialized
        if isinstance(last_msg, dict):
            content = last_msg.get("content", "")
        elif isinstance(last_msg, str):
            content = last_msg
        else:
            content = str(last_msg)
        if content:
            return content

    # Fall back to artifacts summary
    artifacts = final_output.get("artifacts", {})
    if artifacts:
        # Return artifact keys and their content (no truncation)
        parts = []
        for key, value in artifacts.items():
            if key in ("user_request", "conversation_id"):
                continue  # Skip system artifacts
            parts.append(f"[{key}]: {value}")
        if parts:
            return "\n".join(parts)

    return "Error: fork returned no result — empty response from subagent"
