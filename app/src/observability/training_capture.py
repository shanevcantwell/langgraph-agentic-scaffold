# app/src/observability/training_capture.py
"""
Training Data Capture for LAS (LangGraph Agentic Scaffold)

Captures specialist execution context for building real-world test datasets.
Exports to BFCL and Inspect AI formats for use with prompt-prix.

Usage:
    # Enable capture (in config or at runtime)
    from app.src.observability.training_capture import TrainingCapture
    TrainingCapture.enable()

    # Run your workflow normally...

    # Export captured data
    TrainingCapture.export_bfcl("training_data.jsonl")
    TrainingCapture.export_inspect("training_data_inspect.json")
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal
from dataclasses import dataclass, field, asdict
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class OutcomeStatus(str, Enum):
    """Outcome classification for training data labeling."""
    SUCCESS = "success"           # task_is_complete=True, no errors
    FAILURE = "failure"           # Exception raised, validation failed
    PARTIAL = "partial"           # Completed but with warnings/fallbacks
    PENDING_LABEL = "pending"     # Needs human review


@dataclass
class CapturedExecution:
    """Single specialist execution record."""

    # Identity
    id: str                                    # Unique ID for this execution
    timestamp: str                             # ISO timestamp
    specialist_name: str                       # Which specialist ran
    run_id: Optional[str] = None               # LangSmith run ID if available

    # Input Context
    input_messages: List[Dict[str, Any]] = field(default_factory=list)  # Conversation history
    input_scratchpad: Dict[str, Any] = field(default_factory=dict)      # Transient state
    input_artifacts: Dict[str, Any] = field(default_factory=dict)       # Structured outputs
    gathered_context: Optional[str] = None                               # From Facilitator

    # Tools Available (for Router/tool-calling specialists)
    tools_available: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Optional[str] = None          # "required", "auto", "none"

    # Output
    output_scratchpad: Dict[str, Any] = field(default_factory=dict)
    output_artifacts: Dict[str, Any] = field(default_factory=dict)
    tool_calls_made: List[Dict[str, Any]] = field(default_factory=list)  # Actual function calls
    llm_response_raw: Optional[str] = None     # Raw LLM output for debugging

    # Outcome
    outcome: OutcomeStatus = OutcomeStatus.PENDING_LABEL
    outcome_reason: Optional[str] = None       # Why this classification
    error_message: Optional[str] = None        # If failure

    # Routing (for RouterSpecialist)
    routing_decision: Optional[str] = None     # Which specialist was chosen
    routing_alternatives: List[str] = field(default_factory=list)  # Other valid options

    # Metadata
    model_id: Optional[str] = None             # Which LLM was used
    latency_ms: Optional[int] = None           # Execution time
    token_count: Optional[int] = None          # If available
    tags: List[str] = field(default_factory=list)  # Custom tags for filtering


class TrainingCapture:
    """
    Singleton for capturing specialist execution data.

    Thread-safe accumulator that can be enabled/disabled at runtime.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._captures: List[CapturedExecution] = []
        self._enabled = False
        self._capture_lock = threading.Lock()
        self._execution_counter = 0
        self._initialized = True

    # =========================================================================
    # Control Methods
    # =========================================================================

    @classmethod
    def enable(cls):
        """Enable training data capture."""
        instance = cls()
        instance._enabled = True
        logger.info("TrainingCapture enabled")

    @classmethod
    def disable(cls):
        """Disable training data capture."""
        instance = cls()
        instance._enabled = False
        logger.info("TrainingCapture disabled")

    @classmethod
    def is_enabled(cls) -> bool:
        return cls()._enabled

    @classmethod
    def clear(cls):
        """Clear all captured data."""
        instance = cls()
        with instance._capture_lock:
            instance._captures = []
            instance._execution_counter = 0
        logger.info("TrainingCapture cleared")

    @classmethod
    def count(cls) -> int:
        """Return number of captured executions."""
        return len(cls()._captures)

    # =========================================================================
    # Capture Methods
    # =========================================================================

    @classmethod
    def capture_execution(
        cls,
        specialist_name: str,
        input_state: Dict[str, Any],
        output_result: Dict[str, Any],
        tools_available: Optional[List[Dict]] = None,
        tool_calls_made: Optional[List[Dict]] = None,
        error: Optional[Exception] = None,
        model_id: Optional[str] = None,
        latency_ms: Optional[int] = None,
        run_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Capture a specialist execution.

        Called from BaseSpecialist.execute() wrapper or specialist-specific hooks.

        Returns:
            Capture ID if successful, None if capture disabled
        """
        instance = cls()
        if not instance._enabled:
            return None

        with instance._capture_lock:
            instance._execution_counter += 1
            capture_id = f"las_{specialist_name}_{instance._execution_counter:06d}"

        # Extract input context
        input_messages = cls._serialize_messages(input_state.get("messages", []))
        input_scratchpad = input_state.get("scratchpad", {})
        input_artifacts = input_state.get("artifacts", {})
        gathered_context = input_artifacts.get("gathered_context")

        # Extract output
        output_scratchpad = output_result.get("scratchpad", {})
        output_artifacts = output_result.get("artifacts", {})

        # Determine outcome
        outcome, outcome_reason = cls._classify_outcome(
            specialist_name=specialist_name,
            output_scratchpad=output_scratchpad,
            error=error,
            tool_calls=tool_calls_made,
        )

        # Extract routing info for RouterSpecialist
        routing_decision = None
        routing_alternatives = []
        if specialist_name == "router_specialist":
            routing_decision = output_scratchpad.get("next_specialist")
            if tools_available:
                routing_alternatives = [t.get("function", {}).get("name", t.get("name", ""))
                                       for t in tools_available]

        capture = CapturedExecution(
            id=capture_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            specialist_name=specialist_name,
            run_id=run_id,
            input_messages=input_messages,
            input_scratchpad=cls._safe_serialize(input_scratchpad),
            input_artifacts=cls._safe_serialize(input_artifacts),
            gathered_context=gathered_context,
            tools_available=tools_available or [],
            output_scratchpad=cls._safe_serialize(output_scratchpad),
            output_artifacts=cls._safe_serialize(output_artifacts),
            tool_calls_made=tool_calls_made or [],
            outcome=outcome,
            outcome_reason=outcome_reason,
            error_message=str(error) if error else None,
            routing_decision=routing_decision,
            routing_alternatives=routing_alternatives,
            model_id=model_id,
            latency_ms=latency_ms,
            tags=tags or [],
        )

        with instance._capture_lock:
            instance._captures.append(capture)

        logger.debug(f"Captured execution: {capture_id} ({outcome.value})")
        return capture_id

    @classmethod
    def _classify_outcome(
        cls,
        specialist_name: str,
        output_scratchpad: Dict[str, Any],
        error: Optional[Exception],
        tool_calls: Optional[List[Dict]],
    ) -> tuple[OutcomeStatus, str]:
        """
        Heuristically classify execution outcome.

        Returns:
            (OutcomeStatus, reason_string)
        """
        # Explicit failure
        if error:
            return OutcomeStatus.FAILURE, f"Exception: {type(error).__name__}"

        # Check task_is_complete signal
        task_complete = output_scratchpad.get("task_is_complete", False)
        if task_complete:
            return OutcomeStatus.SUCCESS, "task_is_complete=True"

        # Check for decline (not failure, just routing signal)
        if output_scratchpad.get("decline_task"):
            return OutcomeStatus.PARTIAL, "Specialist declined task"

        # Check for self-correction request
        if output_scratchpad.get("self_correction_request"):
            return OutcomeStatus.PARTIAL, "Self-correction requested"

        # Router-specific: check if valid routing decision was made
        if specialist_name == "router_specialist":
            next_spec = output_scratchpad.get("next_specialist")
            if next_spec:
                return OutcomeStatus.SUCCESS, f"Routed to {next_spec}"
            return OutcomeStatus.FAILURE, "No routing decision"

        # Tool-calling specialists: check if expected tool was called
        if tool_calls:
            return OutcomeStatus.SUCCESS, f"Made {len(tool_calls)} tool call(s)"

        # Default: needs human review
        return OutcomeStatus.PENDING_LABEL, "Outcome unclear - needs review"

    @classmethod
    def _serialize_messages(cls, messages: List) -> List[Dict[str, Any]]:
        """Convert LangChain messages to serializable dicts."""
        serialized = []
        for msg in messages:
            if hasattr(msg, "type") and hasattr(msg, "content"):
                serialized.append({
                    "role": msg.type if msg.type != "human" else "user",
                    "content": msg.content,
                })
            elif isinstance(msg, dict):
                serialized.append(msg)
        return serialized

    @classmethod
    def _safe_serialize(cls, obj: Any) -> Any:
        """Safely serialize object, handling non-JSON types."""
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            if isinstance(obj, dict):
                return {k: cls._safe_serialize(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [cls._safe_serialize(v) for v in obj]
            else:
                return str(obj)

    # =========================================================================
    # Export Methods
    # =========================================================================

    @classmethod
    def export_bfcl(cls, filepath: str, filter_tags: Optional[List[str]] = None) -> int:
        """
        Export captures to BFCL (Berkeley Function Calling Leaderboard) format.

        Args:
            filepath: Output JSONL file path
            filter_tags: Only include captures with these tags (optional)

        Returns:
            Number of records exported
        """
        instance = cls()
        captures = instance._captures

        if filter_tags:
            captures = [c for c in captures if any(t in c.tags for t in filter_tags)]

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(path, "w") as f:
            for capture in captures:
                bfcl_record = cls._to_bfcl(capture)
                if bfcl_record:
                    f.write(json.dumps(bfcl_record) + "\n")
                    count += 1

        logger.info(f"Exported {count} records to BFCL format: {filepath}")
        return count

    @classmethod
    def _to_bfcl(cls, capture: CapturedExecution) -> Optional[Dict[str, Any]]:
        """Convert CapturedExecution to BFCL format."""
        # Build question (messages)
        question = []

        # Add system prompt from scratchpad if available
        system_prompt = capture.input_scratchpad.get("system_prompt")
        if system_prompt:
            question.append({"role": "system", "content": system_prompt})

        # Add conversation messages
        question.extend(capture.input_messages)

        # Add gathered context as system context
        if capture.gathered_context:
            question.append({
                "role": "system",
                "content": f"[Gathered Context]\n{capture.gathered_context}"
            })

        # Build function definitions from tools_available
        functions = []
        for tool in capture.tools_available:
            if "function" in tool:
                # Already in OpenAI format
                func = tool["function"]
            else:
                # Flat format
                func = tool
            functions.append({
                "name": func.get("name", "unknown"),
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })

        # Build ground truth from actual tool calls
        ground_truth = []
        for call in capture.tool_calls_made:
            if "function" in call:
                ground_truth.append({
                    "name": call["function"].get("name"),
                    "arguments": call["function"].get("arguments", {}),
                })
            else:
                ground_truth.append({
                    "name": call.get("name"),
                    "arguments": call.get("arguments", {}),
                })

        # For router, ground truth is the routing decision
        if capture.specialist_name == "router_specialist" and capture.routing_decision:
            ground_truth = [{
                "name": "route",
                "arguments": {"specialist": capture.routing_decision},
            }]

        return {
            "id": capture.id,
            "question": question,
            "function": functions,
            "ground_truth": ground_truth,
            "metadata": {
                "specialist": capture.specialist_name,
                "outcome": capture.outcome.value,
                "outcome_reason": capture.outcome_reason,
                "model_id": capture.model_id,
                "timestamp": capture.timestamp,
                "tags": capture.tags,
            },
        }

    @classmethod
    def export_inspect(cls, filepath: str, filter_tags: Optional[List[str]] = None) -> int:
        """
        Export captures to Inspect AI format.

        Args:
            filepath: Output JSON file path
            filter_tags: Only include captures with these tags (optional)

        Returns:
            Number of records exported
        """
        instance = cls()
        captures = instance._captures

        if filter_tags:
            captures = [c for c in captures if any(t in c.tags for t in filter_tags)]

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        samples = []
        for capture in captures:
            sample = cls._to_inspect(capture)
            if sample:
                samples.append(sample)

        output = {
            "name": "las_training_data",
            "description": "Real-world LAS execution captures",
            "samples": samples,
        }

        with open(path, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Exported {len(samples)} records to Inspect AI format: {filepath}")
        return len(samples)

    @classmethod
    def _to_inspect(cls, capture: CapturedExecution) -> Optional[Dict[str, Any]]:
        """Convert CapturedExecution to Inspect AI format."""
        # Get last user message as input
        user_messages = [m for m in capture.input_messages if m.get("role") == "user"]
        input_text = user_messages[-1]["content"] if user_messages else ""

        # Build system prompt
        system_messages = [m for m in capture.input_messages if m.get("role") == "system"]
        system_prompt = system_messages[0]["content"] if system_messages else ""

        # Add gathered context to system prompt
        if capture.gathered_context:
            system_prompt += f"\n\n[Gathered Context]\n{capture.gathered_context}"

        # Build tools in OpenAI format
        tools = []
        for tool in capture.tools_available:
            if "function" in tool:
                tools.append(tool)
            else:
                tools.append({"type": "function", "function": tool})

        # Build target based on actual outcome
        target = {}
        if capture.tool_calls_made:
            target["tool_calls"] = capture.tool_calls_made
        if capture.routing_decision:
            target["routing"] = capture.routing_decision

        return {
            "id": capture.id,
            "input": input_text,
            "metadata": {
                "specialist": capture.specialist_name,
                "outcome": capture.outcome.value,
                "outcome_reason": capture.outcome_reason,
                "model_id": capture.model_id,
                "timestamp": capture.timestamp,
                "system_prompt": system_prompt,
                "tags": capture.tags,
            },
            "target": target,
            "tools": tools,
            "tool_choice": capture.tool_choice or "auto",
        }

    @classmethod
    def export_raw(cls, filepath: str) -> int:
        """Export all captures as raw JSON (for debugging/analysis)."""
        instance = cls()
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        records = [asdict(c) for c in instance._captures]
        # Convert enum to string
        for r in records:
            r["outcome"] = r["outcome"].value if isinstance(r["outcome"], OutcomeStatus) else r["outcome"]

        with open(path, "w") as f:
            json.dump(records, f, indent=2)

        logger.info(f"Exported {len(records)} raw records: {filepath}")
        return len(records)

    # =========================================================================
    # Query Methods
    # =========================================================================

    @classmethod
    def get_captures(
        cls,
        specialist: Optional[str] = None,
        outcome: Optional[OutcomeStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[CapturedExecution]:
        """Query captured executions with filters."""
        instance = cls()
        results = instance._captures

        if specialist:
            results = [c for c in results if c.specialist_name == specialist]
        if outcome:
            results = [c for c in results if c.outcome == outcome]
        if tags:
            results = [c for c in results if any(t in c.tags for t in tags)]

        return results

    @classmethod
    def summary(cls) -> Dict[str, Any]:
        """Get summary statistics of captured data."""
        instance = cls()
        captures = instance._captures

        by_specialist = {}
        by_outcome = {}

        for c in captures:
            by_specialist[c.specialist_name] = by_specialist.get(c.specialist_name, 0) + 1
            by_outcome[c.outcome.value] = by_outcome.get(c.outcome.value, 0) + 1

        return {
            "total": len(captures),
            "by_specialist": by_specialist,
            "by_outcome": by_outcome,
            "enabled": instance._enabled,
        }
