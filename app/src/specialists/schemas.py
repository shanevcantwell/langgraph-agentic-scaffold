from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal

class SystemPlan(BaseModel):
    """A structured plan for a software system or component."""
    plan_summary: str = Field(description="A brief, human-readable summary of the proposed plan.")
    refinement_cycles: Optional[int] = Field(
        default=1,
        description="The number of times a specialist like WebBuilder should iterate on its work. Set this if the user asks for refinement or multiple iterations."
    )
    required_components: List[str] = Field(description="A list of software components or modules to be developed.")
    execution_steps: List[str] = Field(description="A sequence of high-level steps to implement the plan.")

class WebContent(BaseModel):
    """A self-contained HTML document."""
    html_document: str = Field(description="The complete, self-contained HTML document as a string, ready to be saved and viewed in a browser.")

class ExtractedData(BaseModel):
    """A schema for structured data extracted from text."""
    extracted_json: Optional[Dict[str, Any]] = Field(default=None, description="The structured data extracted from the text, conforming to the user's request.")

class Sentiment(BaseModel):
    """A schema for sentiment classification."""
    sentiment: Literal["positive", "negative", "neutral"] = Field(description="The classified sentiment of the text.")
