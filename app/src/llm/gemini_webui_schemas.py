"""
Pydantic schemas for Gemini Web UI DOM extraction and validation.

These schemas provide fail-fast validation when Google changes the Gemini UI structure.
When validation fails, the error message shows exactly which field is missing, making
maintenance straightforward.

Reference: docs/ADR/ADR-DISTILL-006_GeminiWebUI_Adapter.md
Reference Implementation: /home/shane/github/shanevcantwell/gemini-exporter/content.js
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List


class ThinkingStage(BaseModel):
    """
    Represents one stage of thinking (e.g., "Understanding the Request").

    Extracted from bold headers + following text in model-thoughts container.
    Maps to gemini-exporter SCHEMA.md lines 86-91.
    """
    stage_name: str = Field(
        description="Stage header from bold/strong element (e.g., 'Understanding the Request')"
    )
    text: str = Field(
        description="Stage reasoning content (paragraphs following the header)"
    )

    @field_validator('stage_name')
    @classmethod
    def stage_name_not_empty(cls, v):
        if not v.strip():
            raise ValueError("stage_name cannot be empty")
        return v.strip()

    @field_validator('text')
    @classmethod
    def text_not_empty(cls, v):
        if not v.strip():
            raise ValueError("stage text cannot be empty")
        return v.strip()


class ThinkingBlock(BaseModel):
    """
    Container for all thinking stages in a response.

    Extracted from [data-test-id='model-thoughts'] DOM container.
    """
    stages: List[ThinkingStage] = Field(
        description="Ordered list of thinking stages",
        min_length=1  # If thinking exists, must have at least 1 stage
    )


class ConversationContainer(BaseModel):
    """
    Represents one .conversation-container DOM element (one complete turn).

    Maps to gemini-exporter's exchange structure.
    """
    container_id: Optional[str] = Field(
        None,
        description="DOM element ID (e.g., 'c61fbdc59e290cd9') for timestamp merging"
    )
    user_text: str = Field(
        description="User's message from .user-query-container"
    )
    thinking: Optional[ThinkingBlock] = Field(
        None,
        description="Thinking stages if present, None otherwise"
    )
    response_text: str = Field(
        description="Gemini's response from .markdown-main-panel (thinking excluded)"
    )

    @field_validator('user_text')
    @classmethod
    def user_text_not_empty(cls, v):
        if not v.strip():
            raise ValueError("user_text cannot be empty")
        return v.strip()

    @field_validator('response_text')
    @classmethod
    def response_text_not_empty(cls, v):
        if not v.strip():
            raise ValueError("response_text cannot be empty")
        return v.strip()


class GeminiUIResponse(BaseModel):
    """
    Complete validated response from Gemini web UI extraction.

    This is the top-level schema returned by _extract_and_validate().
    """
    conversation_id: str = Field(
        description="Gemini conversation ID from URL (e.g., '210cdaa5f25daa51')"
    )
    container: ConversationContainer = Field(
        description="The extracted conversation container"
    )

    @field_validator('conversation_id')
    @classmethod
    def conversation_id_valid(cls, v):
        if not v or len(v) < 10:
            raise ValueError("conversation_id must be valid hex string")
        return v


# Helper for adapter return format (not used for validation, just documentation)
class AdapterReturnFormat:
    """
    Documents the format returned by GeminiWebUIAdapter.invoke()

    This is NOT a Pydantic model - just documentation.
    Actual return is a plain dict matching this structure.
    """
    text_response: str  # From GeminiUIResponse.container.response_text
    thinking_stages: Optional[List[dict]]  # From ThinkingBlock.stages (as dicts)
