"""
fork() — Recursive LAS invocation for context-isolated subtasks.

ADR-CORE-045: LAS as Recursive Tool.

Spawns a fresh LAS graph invocation in-process via graph.invoke(). The child
gets its own context window, full tool access, and complete pipeline
(SA → Triage → Router → Specialist → EI → Archiver). The child runs ALL
of LAS — only Archiver disk write is suppressed (via subagent scratchpad flag).

Returns the child's full final state dict. The calling specialist extracts
what it needs (typically artifacts["final_user_response.md"]).

Use when processing multiple independent items that each require LLM
reasoning — each fork prevents context accumulation in the parent.
"""
import logging
import uuid
from typing import Any, Dict, Optional

from ..graph.state_factory import create_initial_state
from ..utils.cancellation_manager import CancellationManager

logger = logging.getLogger(__name__)

# Default recursion depth limit for nested fork() chains.
_DEFAULT_MAX_DEPTH = 3


def dispatch_fork(
    compiled_graph,
    prompt: str,
    context: str | None = None,
    parent_run_id: Optional[str] = None,
    fork_depth: int = 0,
    max_depth: int = _DEFAULT_MAX_DEPTH,
    recursion_limit: int = 25,
) -> Dict[str, Any]:
    """
    Spawn a fresh LAS invocation to handle a subtask.

    Args:
        compiled_graph: The compiled LangGraph Pregel graph. Passed by the
                        specialist from self._compiled_graph (injected by
                        WorkflowRunner after build).
        prompt: Task prompt for the child. Written like a task for a
                skilled colleague — say what you need, not how to do it.
        context: Optional document content or context to pass. Only what
                 the subagent needs for this specific subtask.
        parent_run_id: Run ID of the parent workflow. Used to register
                       the parent→child relationship in CancellationManager
                       for cascade cancellation.
        fork_depth: Current recursion depth (0 = top-level invocation).
        max_depth: Maximum allowed recursion depth before refusing to fork.
        recursion_limit: LangGraph recursion limit for the child graph
                         (max node transitions per invocation).

    Returns:
        The child's final GraphState dict on success, or a dict with an
        "error" key on failure.
    """
    if fork_depth >= max_depth:
        msg = f"Fork depth limit ({max_depth}) reached — refusing to spawn deeper"
        logger.warning(f"fork(): {msg}")
        return {"error": msg}

    child_run_id = str(uuid.uuid4())

    logger.info(
        f"fork(): Spawning subagent — prompt length={len(prompt)}, "
        f"context={'yes' if context else 'no'}, "
        f"depth={fork_depth}/{max_depth}, "
        f"parent_run_id={parent_run_id or 'none'}, "
        f"child_run_id={child_run_id}"
    )

    if parent_run_id:
        CancellationManager.register_child(parent_run_id, child_run_id)

    initial_state = create_initial_state(
        goal=prompt,
        text_to_process=context,
        subagent=True,
        run_id=child_run_id,
        additional_scratchpad={"fork_depth": fork_depth + 1},
    )

    try:
        final_state = compiled_graph.invoke(
            initial_state,
            config={"recursion_limit": recursion_limit},
        )
        logger.info(f"fork(): Child {child_run_id} completed successfully")
        return final_state

    except Exception as e:
        msg = f"Fork failed: {e}"
        logger.error(f"fork(): {msg}", exc_info=True)
        return {"error": msg}

    finally:
        CancellationManager.clear_cancellation(child_run_id)


def extract_fork_result(child_state: Dict[str, Any]) -> str:
    """
    Extract a concise result string from a child invocation's final state.

    The child runs full LAS including EndSpecialist, which writes
    final_user_response.md to artifacts. This is the canonical result.

    Args:
        child_state: The dict returned by dispatch_fork().

    Returns:
        Result string, or an error message prefixed with "Error:".
    """
    # Error from dispatch_fork() itself (depth limit, exception)
    if "error" in child_state:
        return f"Error: {child_state['error']}"

    # Canonical result: EndSpecialist writes this after synthesis
    artifacts = child_state.get("artifacts", {})
    if artifacts.get("final_user_response.md"):
        return artifacts["final_user_response.md"]

    # Error from within the child's execution
    error_report = child_state.get("scratchpad", {}).get("error_report")
    if error_report:
        return f"Error: {error_report}"

    # Last message fallback
    messages = child_state.get("messages", [])
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None) or str(last)
        if content:
            return content

    return "Error: fork returned no result — empty response from subagent"
