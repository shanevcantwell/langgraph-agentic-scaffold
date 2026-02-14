import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional, List
from .ag_ui_schema import AgUiEvent, EventType

logger = logging.getLogger(__name__)

class AgUiTranslator:
    """
    Translates raw LangGraph stream events into standardized AG-UI events.
    This encapsulates the logic for interpreting the graph's output and 
    formatting it for the frontend.
    """
    def __init__(self):
        self.accumulated_state = {}
        self.run_id = None

    async def translate(self, raw_stream: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[AgUiEvent, None]:
        """
        Consumes the raw stream from WorkflowRunner and yields AgUiEvents.
        """
        async for chunk in raw_stream:
            # 1. Handle Run ID (Start of Workflow)
            if "run_id" in chunk:
                self.run_id = chunk["run_id"]
                yield AgUiEvent(
                    run_id=self.run_id,
                    type=EventType.WORKFLOW_START,
                    source="system",
                    data={"run_id": self.run_id}
                )
                continue

            # 2. Handle thread_id (metadata, not a node)
            if "thread_id" in chunk:
                # Store for interrupt handling but don't emit an event
                continue

            # ADR-CORE-075: Handle conversation_id (metadata, not a node)
            if "conversation_id" in chunk:
                continue

            # 3. Handle Interrupt Events (ADR-CORE-018/042: HitL Clarification)
            if "__interrupt__" in chunk:
                interrupt_data = chunk["__interrupt__"]
                if interrupt_data and len(interrupt_data) > 0:
                    payload = interrupt_data[0]
                    # Handle both object (Interrupt namedtuple) and dict forms
                    value = payload.value if hasattr(payload, 'value') else payload.get("value", {})
                    # Forward the full interrupt payload so the UI can handle both formats:
                    #   Facilitator ASK_USER: {question: "...", reason: "...", action_type: "ask_user"}
                    #   Future/Dialogue:      {questions: [{question, reason}, ...]}
                    event_data = dict(value) if isinstance(value, dict) else {"question": str(value)}
                    event_data["thread_id"] = self.run_id  # Use run_id as thread_id for resume
                    event_data["resumable"] = True
                    yield AgUiEvent(
                        run_id=self.run_id,
                        type=EventType.CLARIFICATION_REQUIRED,
                        source="system",
                        data=event_data
                    )
                # Don't emit WORKFLOW_END - workflow is paused, not complete
                return

            # 4. Handle Node Execution
            for node_name, node_output in chunk.items():
                # Emit NODE_START event
                yield AgUiEvent(
                    run_id=self.run_id,
                    type=EventType.NODE_START,
                    source=node_name,
                    data={"status": f"Starting {node_name}..."}
                )

                # Emit Status Update (for backward compatibility)
                yield AgUiEvent(
                    run_id=self.run_id,
                    type=EventType.STATUS_UPDATE,
                    source=node_name,
                    data={"status": f"Executing specialist: {node_name}..."}
                )

                # Emit Log (for UI ticker)
                yield AgUiEvent(
                    run_id=self.run_id,
                    type=EventType.LOG,
                    source=node_name,
                    data={"message": f"Entering node: {node_name}"}
                )

                # 3. Handle Errors
                if isinstance(node_output, dict):
                    scratchpad = node_output.get("scratchpad", {})
                    error_report = scratchpad.get("error_report", "") if isinstance(scratchpad, dict) else ""
                    if "error" in node_output or error_report:
                        error_msg = node_output.get("error", "Unknown error")
                        yield AgUiEvent(
                            run_id=self.run_id,
                            type=EventType.ERROR,
                            source=node_name,
                            data={"error": error_msg, "error_report": error_report}
                        )

                    # 4. Accumulate State (Reducer Logic)
                    self._update_accumulated_state(node_output)

                    # Emit NODE_END event with output data
                    yield AgUiEvent(
                        run_id=self.run_id,
                        type=EventType.NODE_END,
                        source=node_name,
                        data={
                            "scratchpad": scratchpad,
                            "artifacts": node_output.get("artifacts", {}),
                            "status": f"Completed {node_name}"
                        }
                    )

        # 5. End of Workflow
        yield self._create_workflow_end_event()

    def _update_accumulated_state(self, node_output: Dict[str, Any]):
        """
        Merges node output into the accumulated state, respecting GraphState reducer semantics.
        """
        if not self.accumulated_state:
            self.accumulated_state = {}
            for key, value in node_output.items():
                if isinstance(value, list):
                    self.accumulated_state[key] = list(value)
                elif isinstance(value, dict):
                    self.accumulated_state[key] = dict(value)
                else:
                    self.accumulated_state[key] = value
        else:
            for key, value in node_output.items():
                if key in ["messages", "routing_history"]:
                    # operator.add: append to lists
                    self.accumulated_state.setdefault(key, []).extend(value if isinstance(value, list) else [value])
                elif key in ["artifacts", "scratchpad"]:
                    # operator.ior: merge dictionaries
                    self.accumulated_state.setdefault(key, {}).update(value if isinstance(value, dict) else {})
                else:
                    # No annotation: overwrite with latest value
                    self.accumulated_state[key] = value

    def _create_workflow_end_event(self) -> AgUiEvent:
        """
        Constructs the final WORKFLOW_END event with the summarized state.
        """
        if not self.accumulated_state:
            return AgUiEvent(
                run_id=self.run_id,
                type=EventType.WORKFLOW_END,
                source="system",
                data={"status": "Workflow complete (no state)."}
            )

        artifacts = self.accumulated_state.get("artifacts", {})
        archive_report = artifacts.get("archive_report.md", "")
        html_content = artifacts.get("html_document.html", "")
        scratchpad = self.accumulated_state.get("scratchpad", {})
        messages = self.accumulated_state.get("messages", [])

        # Convert messages to JSON-safe format
        messages_summary = []
        for msg in messages:
            if hasattr(msg, 'content') and hasattr(msg, 'type'):
                messages_summary.append({
                    "type": msg.type,
                    "content": msg.content[:200] + "..." if len(str(msg.content)) > 200 else msg.content
                })
            elif isinstance(msg, dict):
                 messages_summary.append({
                    "type": msg.get("type", "unknown"),
                    "content": str(msg.get("content", ""))[:200] + "..."
                })

        final_state_summary = {
            "routing_history": self.accumulated_state.get("routing_history", []),
            "turn_count": self.accumulated_state.get("turn_count", 0),
            "task_is_complete": self.accumulated_state.get("task_is_complete", False),
            "next_specialist": self.accumulated_state.get("next_specialist"),
            "recommended_specialists": scratchpad.get("recommended_specialists") if isinstance(scratchpad, dict) else None,
            "error_report": scratchpad.get("error_report") if isinstance(scratchpad, dict) else None,
            "artifacts": list(artifacts.keys()) if artifacts else [],
            "scratchpad": {k: (v if not isinstance(v, (dict, list)) or len(str(v)) < 500 else f"<{type(v).__name__} with {len(v)} items>") for k, v in scratchpad.items()},
            "messages_summary": messages_summary
        }

        return AgUiEvent(
            run_id=self.run_id,
            type=EventType.WORKFLOW_END,
            source="system",
            data={
                "status": "Workflow complete.",
                "final_state": final_state_summary,
                "archive": archive_report,
                "html": html_content
            }
        )
