# app/src/llm/tracing.py
"""
LLM Trace Capture for Training Data Generation.

Captures specialist turn traces for fine-tuning and RL datasets. Each trace
captures the full orchestration context: what the specialist saw, what it
produced, and what routing decision was made.

Two-layer capture:
1. Adapter layer: Raw LLM timing and response (captured by adapters)
2. Orchestration layer: Full context (assembled by NodeExecutor)

Output format (in archive llm_traces.jsonl):
    {
      "step": 0,
      "specialist": "triage_architect",
      "specialist_type": "analytical",
      "from": "user",
      "system_prompt": "...",
      "assembled_prompt": "...",
      "context_artifacts": ["filename.ext"],
      "response_text": "...",
      "tool_calls": [],
      "artifacts_produced": ["new_file.html"],
      "routing_decision": "web_builder",
      "latency_ms": 1234,
      "model_id": "gemini-2.0-flash"
    }
"""
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpecialistTurnTrace(BaseModel):
    """
    Schema for a complete specialist turn trace.

    Captures the full orchestration context for RL/fine-tuning datasets.
    """
    # Turn identification
    step: int = Field(..., description="Turn number in the workflow (0-indexed)")
    specialist: str = Field(..., description="Name of the specialist")
    specialist_type: str = Field(..., description="Type from config (llm, hybrid, procedural)")

    # Provenance
    from_source: str = Field(..., description="What triggered this turn (user, previous specialist name)")

    # Input context
    system_prompt: Optional[str] = Field(None, description="System prompt for this specialist")
    assembled_prompt: str = Field(..., description="The assembled user/context prompt sent to LLM")
    context_artifacts: List[str] = Field(default_factory=list, description="Artifact keys available to this specialist")

    # Output
    response_text: Optional[str] = Field(None, description="Text response from the specialist")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="Tool calls made by the LLM")
    artifacts_produced: List[str] = Field(default_factory=list, description="New artifact keys produced")
    scratchpad_signals: Dict[str, Any] = Field(default_factory=dict, description="Scratchpad signals written")

    # Routing
    routing_decision: Optional[str] = Field(None, description="Next specialist decision (for router)")

    # Performance
    latency_ms: int = Field(..., description="Time taken for this turn in milliseconds")
    model_id: str = Field(..., description="Model identifier used")

    # Timestamp
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AdapterTrace(BaseModel):
    """
    Lightweight trace from adapter layer.

    Contains just the LLM-specific data that the adapter can provide.
    NodeExecutor wraps this with orchestration context to create SpecialistTurnTrace.
    """
    latency_ms: int
    model_id: str
    response_type: str  # "text", "json", "tool_call", "error"
    response_text: Optional[str] = None
    response_json: Optional[Dict[str, Any]] = None
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    request_messages_serialized: List[Dict[str, Any]] = Field(default_factory=list)


class TraceAccumulator:
    """
    Thread-local accumulator for adapter traces.

    Adapters capture lightweight traces here. NodeExecutor flushes and wraps
    with orchestration context to create complete SpecialistTurnTrace records.
    """

    def __init__(self):
        self._local = threading.local()

    def _get_traces(self) -> List[AdapterTrace]:
        """Get the thread-local trace list, creating if needed."""
        if not hasattr(self._local, 'traces'):
            self._local.traces = []
        return self._local.traces

    def _get_specialist(self) -> Optional[str]:
        """Get the current specialist name for this thread."""
        return getattr(self._local, 'current_specialist', None)

    def set_current_specialist(self, specialist_name: str) -> None:
        """Set the current specialist name for trace attribution."""
        self._local.current_specialist = specialist_name
        logger.debug(f"TraceAccumulator: Set current specialist to '{specialist_name}'")

    def clear_current_specialist(self) -> None:
        """Clear the current specialist name."""
        self._local.current_specialist = None

    def capture(
        self,
        request: Any,  # StandardizedLLMRequest
        response: Dict[str, Any],
        latency_ms: int,
        model_name: Optional[str]
    ) -> None:
        """
        Capture an adapter-level trace.

        Called by adapters after each invoke() call.
        """
        # Serialize messages for storage
        serialized_messages = []
        for msg in request.messages:
            serialized_messages.append({
                "type": getattr(msg, "type", "unknown"),
                "content": getattr(msg, "content", ""),
                "name": getattr(msg, "name", None),
            })

        # Determine response type and content
        response_type = "unknown"
        response_text = None
        response_json = None
        tool_calls = []

        if "tool_calls" in response and response["tool_calls"]:
            response_type = "tool_call"
            tool_calls = response["tool_calls"]
        elif "json_response" in response:
            response_type = "json"
            response_json = response["json_response"]
        elif "text_response" in response:
            response_type = "text"
            response_text = response["text_response"]
        elif "error" in response:
            response_type = "error"
            response_text = str(response.get("error", "Unknown error"))

        trace = AdapterTrace(
            latency_ms=latency_ms,
            model_id=model_name or "unknown",
            response_type=response_type,
            response_text=response_text,
            response_json=response_json,
            tool_calls=tool_calls,
            request_messages_serialized=serialized_messages
        )

        self._get_traces().append(trace)
        logger.debug(f"TraceAccumulator: Captured adapter trace ({response_type})")

    def flush(self) -> List[AdapterTrace]:
        """
        Flush and return all accumulated adapter traces.

        Called by NodeExecutor to get raw traces for wrapping.
        """
        traces = self._get_traces()
        result = list(traces)
        self._local.traces = []
        return result

    def count(self) -> int:
        """Return the number of accumulated traces."""
        return len(self._get_traces())


# Global singleton instance
_accumulator = TraceAccumulator()


def set_current_specialist(specialist_name: str) -> None:
    """Set the current specialist for trace attribution."""
    _accumulator.set_current_specialist(specialist_name)


def clear_current_specialist() -> None:
    """Clear the current specialist."""
    _accumulator.clear_current_specialist()


def capture_trace(
    request: Any,
    response: Dict[str, Any],
    latency_ms: int,
    model_name: Optional[str]
) -> None:
    """Capture an adapter-level trace."""
    _accumulator.capture(request, response, latency_ms, model_name)


def flush_adapter_traces() -> List[AdapterTrace]:
    """Flush and return all accumulated adapter traces."""
    return _accumulator.flush()


def trace_count() -> int:
    """Return the number of accumulated traces."""
    return _accumulator.count()


def build_specialist_turn_trace(
    adapter_traces: List[AdapterTrace],
    step: int,
    specialist_name: str,
    specialist_type: str,
    from_source: str,
    system_prompt: Optional[str],
    context_artifacts_before: List[str],
    artifacts_produced: List[str],
    scratchpad_signals: Dict[str, Any],
    routing_decision: Optional[str],
    execution_latency_ms: Optional[int] = None,
) -> SpecialistTurnTrace:
    """
    Build a complete SpecialistTurnTrace from adapter traces and orchestration context.

    Called by NodeExecutor after specialist execution.

    Args:
        execution_latency_ms: For procedural specialists (no LLM calls), pass the
            total execution time. If None and adapter_traces is empty, latency will be 0.
    """
    # Aggregate adapter trace data
    # For procedural specialists with no adapter traces, use execution_latency_ms if provided
    total_latency = sum(t.latency_ms for t in adapter_traces) if adapter_traces else (execution_latency_ms or 0)
    model_id = adapter_traces[0].model_id if adapter_traces else "no_llm_call"

    # Extract response content from the last trace (most relevant)
    response_text = None
    tool_calls = []
    assembled_prompt = ""

    if adapter_traces:
        last_trace = adapter_traces[-1]
        response_text = last_trace.response_text
        tool_calls = last_trace.tool_calls

        # Build assembled prompt from request messages
        prompt_parts = []
        for msg in last_trace.request_messages_serialized:
            if msg.get("type") in ("human", "user"):
                prompt_parts.append(str(msg.get("content", "")))
        assembled_prompt = "\n".join(prompt_parts)

        # If JSON response, convert to string representation
        if last_trace.response_json and not response_text:
            import json
            response_text = json.dumps(last_trace.response_json)

    return SpecialistTurnTrace(
        step=step,
        specialist=specialist_name,
        specialist_type=specialist_type,
        from_source=from_source,
        system_prompt=system_prompt,
        assembled_prompt=assembled_prompt,
        context_artifacts=context_artifacts_before,
        response_text=response_text,
        tool_calls=tool_calls,
        artifacts_produced=artifacts_produced,
        scratchpad_signals=scratchpad_signals,
        routing_decision=routing_decision,
        latency_ms=total_latency,
        model_id=model_id,
    )


# Legacy alias for backwards compatibility
def flush_traces() -> List[Dict[str, Any]]:
    """
    Legacy function - returns empty list.
    Use flush_adapter_traces() and build_specialist_turn_trace() instead.
    """
    # Clear any accumulated traces but return empty -
    # NodeExecutor now handles trace building
    _accumulator.flush()
    return []
