from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from pydantic import BaseModel, Field
from enum import Enum

class EventType(str, Enum):
    WORKFLOW_START = "workflow_start"
    NODE_START = "node_start"
    NODE_END = "node_end"
    ARTIFACT_CREATED = "artifact_created"
    ERROR = "error"
    WORKFLOW_END = "workflow_end"
    STATUS_UPDATE = "status_update"
    LOG = "log"
    # ADR-CORE-042: Interrupt events for "Raise Hand" pattern
    CLARIFICATION_REQUIRED = "clarification_required"

class AgUiEvent(BaseModel):
    """
    Standardized event schema for the Agentic-UI (AG-UI).
    This decouples the frontend from the internal LangGraph event structure.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the event")
    run_id: Optional[str] = Field(None, description="The workflow run ID")
    type: EventType = Field(..., description="The type of event")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), description="UTC timestamp")
    source: str = Field(..., description="The component emitting the event (e.g., 'router_specialist')")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")

    class Config:
        use_enum_values = True
