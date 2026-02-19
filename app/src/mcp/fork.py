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
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

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
    request_body: Dict[str, Any] = {
        "input_prompt": prompt,
        "subagent": True,
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

    Fallback chain:
      1. error_report (child failed)
      2. "result" key (subagent-mode streamlined response)
      3. final_user_response.md artifact (canonical concise output)
      4. Last message content (specialist's output)
      5. Error — genuinely empty response
    """
    final_output = data.get("final_output", {})

    # 1. Error report
    if isinstance(final_output, dict) and "error_report" in final_output:
        return f"Error: subagent error — {final_output['error_report']}"

    # 2. Subagent-mode streamlined response (Phase 2: API returns {"result": "..."})
    if isinstance(final_output, dict) and "result" in final_output:
        result = final_output["result"]
        if result:
            return result

    # 3. final_user_response.md — the canonical concise result artifact
    artifacts = final_output.get("artifacts", {})
    if isinstance(artifacts, dict):
        final_response = artifacts.get("final_user_response.md")
        if final_response:
            return final_response

    # 4. Last message content (specialist's output)
    messages = final_output.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if isinstance(last_msg, dict):
            content = last_msg.get("content", "")
        elif isinstance(last_msg, str):
            content = last_msg
        else:
            content = str(last_msg)
        if content:
            return content

    return "Error: fork returned no result — empty response from subagent"
