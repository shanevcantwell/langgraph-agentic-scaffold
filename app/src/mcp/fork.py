"""
fork() — Recursive LAS invocation for context-isolated subtasks.

ADR-CORE-045: LAS as Recursive Tool.

Spawns a fresh LAS graph invocation in-process via graph.invoke(). The child
gets its own context window, full tool access, and complete pipeline
(SA → Triage → Router → Specialist → EI → Archiver). The child runs ALL
of LAS — only Archiver disk write is suppressed (via subagent scratchpad flag).

Returns the child's full final state dict. The calling specialist extracts
what it needs via extract_fork_result().

Callers can specify expected_artifacts — a list of artifact keys the child
should write to. This creates a structured result contract: the parent gets
exactly the artifacts it asked for, the child's working state is discarded.
See #206 for design rationale.

Use when processing multiple independent items that each require LLM
reasoning — each fork prevents context accumulation in the parent.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from ..graph.state_factory import create_initial_state
from ..utils.cancellation_manager import CancellationManager

logger = logging.getLogger(__name__)

# Default recursion depth limit for nested fork() chains.
_DEFAULT_MAX_DEPTH = 3

# Prepended to every child prompt. Sets the frame so models report failures
# honestly instead of fabricating results to satisfy completion pressure.
# See #205 (artifact provenance) for the fabrication problem this addresses.
_CONDITIONING_FRAME = (
    "This is a development environment where failures are expected and "
    "informative. If a tool fails, a capability is unavailable, or you "
    "cannot complete the task, report exactly what happened and what you "
    "tried. A clear failure report is more valuable than a simulated or "
    "fabricated result. Never generate synthetic data to stand in for "
    "real tool output."
)


def _build_child_prompt(
    prompt: str,
    expected_artifacts: List[str] | None = None,
) -> str:
    """
    Assemble the child's goal prompt from caller inputs.

    Prepends the conditioning frame and appends artifact key instructions
    when expected_artifacts are specified. The caller model only provides
    the task and key names — this function handles the prompt engineering.
    """
    parts = [_CONDITIONING_FRAME, "", prompt]

    if expected_artifacts:
        keys_formatted = ", ".join(f"`{k}`" for k in expected_artifacts)
        parts.append("")
        parts.append(
            f"Write your result to the following artifact keys using the "
            f"write_artifact tool: {keys_formatted}. "
            f"These specific keys will be read by the calling process."
        )

    return "\n".join(parts)


def dispatch_fork(
    compiled_graph,
    prompt: str,
    context: str | None = None,
    expected_artifacts: List[str] | None = None,
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
        expected_artifacts: Optional list of artifact keys the child should
                            write results to. When specified, the child prompt
                            includes instructions to write to these keys, and
                            extract_fork_result() returns only these values.
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
    child_prompt = _build_child_prompt(prompt, expected_artifacts)

    logger.info(
        f"fork(): Spawning subagent — prompt length={len(child_prompt)}, "
        f"context={'yes' if context else 'no'}, "
        f"expected_artifacts={expected_artifacts or 'none'}, "
        f"depth={fork_depth}/{max_depth}, "
        f"parent_run_id={parent_run_id or 'none'}, "
        f"child_run_id={child_run_id}"
    )

    if parent_run_id:
        CancellationManager.register_child(parent_run_id, child_run_id)

    initial_state = create_initial_state(
        goal=child_prompt,
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


def extract_fork_result(
    child_state: Dict[str, Any],
    expected_artifacts: List[str] | None = None,
) -> str:
    """
    Extract a concise result from a child invocation's final state.

    When expected_artifacts is provided, returns only those artifact values
    formatted as key: value pairs. Otherwise falls back to the narrative
    response from final_user_response.md.

    Args:
        child_state: The dict returned by dispatch_fork().
        expected_artifacts: If provided, extract only these artifact keys.

    Returns:
        Result string, or an error message prefixed with "Error:".
    """
    # Error from dispatch_fork() itself (depth limit, exception)
    if "error" in child_state:
        return f"Error: {child_state['error']}"

    artifacts = child_state.get("artifacts", {})

    # Structured extraction: return only the requested artifact keys (#206)
    if expected_artifacts:
        results = {}
        missing = []
        for key in expected_artifacts:
            value = artifacts.get(key)
            if value is not None:
                results[key] = value
            else:
                missing.append(key)

        if missing:
            logger.warning(
                f"extract_fork_result: child did not write expected artifacts: {missing}"
            )

        if results:
            # Format as readable key-value pairs for the react_step observation
            parts = [f"{k}: {v}" for k, v in results.items()]
            if missing:
                parts.append(f"(missing artifacts: {', '.join(missing)})")
            return "\n".join(parts)

        # No requested artifacts found at all — fall through to standard chain
        logger.warning(
            "extract_fork_result: none of the expected artifacts were produced, "
            "falling back to standard extraction"
        )

    # Canonical result: EndSpecialist writes this after synthesis
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
