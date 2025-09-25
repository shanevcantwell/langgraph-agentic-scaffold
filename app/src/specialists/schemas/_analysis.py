# app/src/specialists/schemas/_analysis.py
from typing import List
from pydantic import BaseModel, Field


class TextAnalysis(BaseModel):
    """
    A structured analysis of a block of text, including a summary and key points.
    """

    summary: str = Field(..., description="A concise summary of the text.")
    main_points: List[str] = Field(
        ..., description="A list of the main points or takeaways from the text."
    )