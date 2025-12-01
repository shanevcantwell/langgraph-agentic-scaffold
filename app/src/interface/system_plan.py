from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field

class ExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CLARIFICATION_REQUIRED = "clarification_required" # ADR-CORE-018

class ExecutionStep(BaseModel):
    step_number: int
    capability: str = Field(..., description="The capability to use (e.g., 'search', 'browse')")
    assigned_to: str = Field(default="web_specialist", description="The specialist assigned to execute this step")
    params: Dict[str, Any] = Field(..., description="Parameters for the capability")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # ADR-CORE-018 HitL Hooks
    clarification_question: Optional[str] = None
    clarification_context: Optional[Dict[str, Any]] = None

class SystemPlan(BaseModel):
    id: str = Field(..., description="Unique ID for the plan")
    goal: str = Field(..., description="The overall goal of this plan")
    steps: List[ExecutionStep] = Field(default_factory=list)
    status: ExecutionStatus = Field(default=ExecutionStatus.IN_PROGRESS)
    current_step_index: int = Field(default=0, description="Index of the current step being executed")
    
    def get_current_step(self) -> Optional[ExecutionStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None
