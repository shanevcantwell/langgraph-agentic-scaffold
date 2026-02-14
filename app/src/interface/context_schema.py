from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class ContextActionType(str, Enum):
    RESEARCH = "research"
    READ_FILE = "read_file"
    SUMMARIZE = "summarize"
    LIST_DIRECTORY = "list_directory"
    ASK_USER = "ask_user"  # On hold — ADR-032 replaces with help_needed[type="clarification"]

class ContextAction(BaseModel):
    type: ContextActionType
    target: str = Field(..., description="The query, file path, or text to process")
    description: str = Field(..., description="Why this action is needed")
    strategy: Optional[str] = Field(
        default=None,
        description="The specific strategy or provider to use (e.g. 'google', 'duckduckgo', 'fast', 'detailed'). Leave null for default."
    )

class ContextPlan(BaseModel):
    """Triage's forced-tool-call wire format. Not persisted as an artifact —
    actions flow to scratchpad['triage_actions'], reasoning to scratchpad['triage_reasoning'].
    """
    actions: List[ContextAction] = Field(default_factory=list)
    reasoning: str = Field(..., description="The reasoning behind the plan")
