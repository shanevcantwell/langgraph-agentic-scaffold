# app/src/specialists/schemas/_data.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any

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

class CodeExecutionParams(BaseModel):
    """Parameters for executing a block of code."""
    language: str = Field(..., description="The programming language of the code to execute (e.g., 'python', 'bash').")
    code: str = Field(..., description="The block of code to execute.")
