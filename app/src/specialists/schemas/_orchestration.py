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
    required_components: List[str] = Field(default_factory=list, description="A list of technologies, libraries, or assets needed.")
    execution_steps: List[str] = Field(..., description="A list of detailed, sequential steps to implement the plan.")
    acceptance_criteria: str = Field(
        default="",
        description="What the completed work looks like. Describe verifiable outcomes a reviewer could check — not the process, but the result."
    )

class CodeExecutionParams(BaseModel):
    """
    The parameters for executing a block of code in a specified language.
    """
    language: str = Field(
        ...,
        description="The programming language of the code to execute (e.g., 'python', 'bash').",
    )
    code: str = Field(
        ...,
        description="The block of code to be executed.",
    )
