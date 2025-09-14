# app/src/specialists/schemas/_orchestration.py
from pydantic import BaseModel, Field
from typing import List

class TriageRecommendations(BaseModel):
    """A model for the Triage specialist's recommendations."""
    recommended_specialists: List[str] = Field(
        ...,
        description="A list of specialist names that are best suited to handle the user's request. The names MUST be chosen from the list of AVAILABLE SPECIALISTS provided in the prompt."
    )

class SystemPlan(BaseModel):
    """A model for the Systems Architect's technical plan."""
    plan_summary: str = Field(..., description="A concise, one-sentence summary of the plan.")
    required_components: List[str] = Field(..., description="A list of technologies, libraries, or assets needed.")
    execution_steps: List[str] = Field(..., description="A list of detailed, sequential steps to implement the plan.")
    refinement_cycles: int = Field(default=1, description="The number of refinement cycles (e.g., with a critic) to perform.")

class Critique(BaseModel):
    """A structured critique of a generated artifact, used by the CriticSpecialist."""
    overall_assessment: str = Field(..., description="A brief, one-paragraph summary of the critique, assessing how well the artifact meets the requirements.")
    points_for_improvement: List[str] = Field(..., description="A list of specific, actionable points of feedback for what to change or add in the next iteration.")
    positive_feedback: List[str] = Field(..., description="Specific aspects of the artifact that were well-executed and should be kept or built upon.")