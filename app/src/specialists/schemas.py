# app/src/specialists/schemas.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any

# --- General & Web ---
class WebContent(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for web content."""
    html_document: str = Field(
        ...,
        description="The full, self-contained HTML document as a single string."
    )

# --- Orchestration & Routing ---
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


# --- File Operations ---
class ReadFileParams(BaseModel):
    """Parameters for reading the contents of a file."""
    file_path: str = Field(..., description="The relative path to the file to be read.")

class WriteFileParams(BaseModel):
    """Parameters for writing content to a file."""
    file_path: str = Field(..., description="The relative path to the file to be written.")
    content: str = Field(..., description="The content to write into the file.")

class ListDirectoryParams(BaseModel):
    """Parameters for listing the contents of a directory."""
    dir_path: str = Field(default=".", description="The relative path to the directory to be listed.")

# --- Data & Analysis ---
class ExtractedData(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for data extraction."""
    extracted_json: Dict[str, Any]

class AnalysisResult(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for text analysis."""
    summary: str
    main_points: List[str]

class Sentiment(BaseModel):
    """A Pydantic model for sentiment classification."""
    sentiment: str = Field(..., description="The sentiment of the text, e.g., 'positive', 'negative', 'neutral'.")
