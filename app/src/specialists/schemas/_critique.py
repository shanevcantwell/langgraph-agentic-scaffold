from typing import List, Literal, Optional
from pydantic import BaseModel, Field

class Critique(BaseModel):
    """A structured critique of an artifact."""
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
    # --- NEW FIELD ---
    # This field acts as a signal from the strategy to the host, indicating
    # that the critique itself failed due to a parsing error, not that the
    # artifact being reviewed was flawed.
    is_parse_error: bool = Field(
        default=False,
        description="A flag to indicate if the critique process failed due to a parsing error."
    )
