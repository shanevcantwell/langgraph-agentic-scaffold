# app/src/specialists/schemas/_web.py
from pydantic import BaseModel, Field

class WebContent(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for web content."""
    html_document: str = Field(
        ...,
        description="The full, self-contained HTML document as a single string."
    )