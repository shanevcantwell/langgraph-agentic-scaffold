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
    actions: List[ContextAction] = Field(default_factory=list)
    reasoning: str = Field(..., description="The reasoning behind the plan")
    recommended_specialists: List[str] = Field(
        default_factory=list,
        description="List of specialist names recommended to handle the user's request after context gathering. Must be chosen from the AVAILABLE SPECIALISTS provided in the prompt."
    )
