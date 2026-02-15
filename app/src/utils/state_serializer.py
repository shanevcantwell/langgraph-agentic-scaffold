# app/src/utils/state_serializer.py
"""
State serialization for SSE snapshots and archive timeline.

Consolidates serialization logic previously duplicated across runner.py,
api.py, and translator.py. Used by SafeExecutor to build timeline entries
and by SSE formatters to emit STATE_SNAPSHOT events.

CRITICAL: No truncation. Full data preserved per project directive.
The Dockyard architecture (ADR-MCP-002) will handle size concerns structurally.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, messages_to_dict
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def make_serializable(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable objects.

    Handles LangChain BaseMessage lists, Pydantic models, datetimes,
    and nested dicts/lists. Returns JSON-safe primitives.
    """
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], BaseMessage):
            return messages_to_dict(obj)
        return [make_serializable(item) for item in obj]
    elif isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def build_timeline_entry(
    *,
    state: Dict[str, Any],
    update: Dict[str, Any],
    specialist_name: str,
    step: int,
    latency_ms: int = 0,
    system_prompt: Optional[str] = None,
    assembled_prompt: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single state timeline entry for archive and SSE emission.

    Captures the accumulated state AFTER this specialist's update is applied.
    The entry includes both the pre-existing state and this specialist's
    contribution, simulating reducer application.

    The ``prompts`` section captures what the backing LLM actually saw:
    - system_prompt + assembled_prompt for non-react specialists
    - react_trace (from scratchpad) for react-step specialists (PD, TA)
    """
    # Simulate reducer application for the snapshot
    merged_artifacts = dict(state.get("artifacts", {}))
    merged_artifacts.update(update.get("artifacts", {}))

    merged_scratchpad = dict(state.get("scratchpad", {}))
    merged_scratchpad.update(update.get("scratchpad", {}))

    merged_routing = list(state.get("routing_history", []))
    merged_routing.extend(update.get("routing_history", []))

    # Extract react_trace if a react-step specialist wrote it
    react_trace = merged_scratchpad.pop("react_trace", None)

    # Extract and consume im_decision so it doesn't go stale
    im_decision = merged_scratchpad.get("im_decision")

    # Build prompts section
    prompts: Dict[str, Any] = {}
    if system_prompt:
        prompts["system_prompt"] = system_prompt
    if assembled_prompt:
        prompts["assembled_prompt"] = assembled_prompt
    if model_id:
        prompts["model_id"] = model_id
    if react_trace is not None:
        prompts["react_trace"] = react_trace

    entry = {
        "step": step,
        "specialist": specialist_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms,
        "routing_history": merged_routing,
        "turn_count": update.get("turn_count", state.get("turn_count", 0)),
        "task_is_complete": update.get(
            "task_is_complete", state.get("task_is_complete", False)
        ),
        "next_specialist": update.get(
            "next_specialist", state.get("next_specialist")
        ),
        "artifact_keys": list(merged_artifacts.keys()),
        "artifacts": make_serializable(merged_artifacts),
        "scratchpad": make_serializable(merged_scratchpad),
        "messages_count": (
            len(state.get("messages", []))
            + len(update.get("messages", []))
        ),
    }

    if im_decision:
        entry["im_decision"] = im_decision
    if prompts:
        entry["prompts"] = prompts

    return entry
