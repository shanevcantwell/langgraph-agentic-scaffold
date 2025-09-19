from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class Critique(BaseModel):
    """A structured critique of an artifact. This is a pure data model."""
    decision: Literal["ACCEPT", "REVISE"] = Field(
        ...,
        description="The final decision on whether the artifact is acceptable or needs revision."
    )
    overall_assessment: str = Field(
        ...,
        description="A high-level summary of the critique."
    )
    points_for_improvement: Optional[List[str]] = Field(
        default_factory=list,
        description="Specific, actionable points for how to improve the artifact."
    )
    positive_feedback: Optional[List[str]] = Field(
        default_factory=list,
        description="What was done well and should be kept."
    )
