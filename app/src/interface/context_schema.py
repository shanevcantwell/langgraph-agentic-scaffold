from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class ContextActionType(str, Enum):
    RESEARCH = "research"
    READ_FILE = "read_file"
    SUMMARIZE = "summarize"

class ContextAction(BaseModel):
    type: ContextActionType
    target: str = Field(..., description="The query, file path, or text to process")
    description: str = Field(..., description="Why this action is needed")

class ContextPlan(BaseModel):
    actions: List[ContextAction] = Field(default_factory=list)
    reasoning: str = Field(..., description="The reasoning behind the plan")
