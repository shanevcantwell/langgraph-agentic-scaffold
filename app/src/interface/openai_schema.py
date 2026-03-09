"""
OpenAI-compatible API schema for the Two-Headed Architecture (ADR-UI-003).

Chat Head only — no vendor extensions, no las_metadata.
Standard ChatCompletionRequest/Response/Chunk models that any OpenAI client can consume.
"""
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pydantic import BaseModel, Field
import time
import uuid


# --- Request Models ---

class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str = Field(..., description="The role of the message author: system, user, or assistant")
    content: Union[str, List[Dict[str, Any]]] = Field(
        ...,
        description="The content of the message. String for text, list of content parts for multimodal."
    )


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = Field(
        "las-default",
        description="Routing profile selector (e.g., 'las-default', 'las-simple', 'las-research')."
    )
    messages: List[ChatMessage] = Field(
        ...,
        description="The conversation messages. Last user message becomes the goal."
    )
    stream: bool = Field(
        False,
        description="If True, stream back partial responses as SSE."
    )
    stream_options: Optional[Dict[str, Any]] = Field(
        None,
        description="Options for streaming (e.g., include_usage)."
    )
    # LAS extension: conversation threading (ignored by standard clients)
    conversation_id: Optional[str] = Field(
        None,
        description="Links turns in a multi-turn conversation. Returned by server on first turn."
    )


# --- Response Models ---

class ChatCompletionMessage(BaseModel):
    """A message in a chat completion response."""
    role: str = "assistant"
    content: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    """A single choice in a chat completion response."""
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: Optional[str] = "stop"


class UsageInfo(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response (non-streaming)."""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "las-default"
    choices: List[ChatCompletionChoice] = Field(default_factory=list)
    usage: UsageInfo = Field(default_factory=UsageInfo)


# --- Streaming Models ---

class DeltaContent(BaseModel):
    """Delta content for streaming responses."""
    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    """A single choice in a streaming chunk."""
    index: int = 0
    delta: DeltaContent = Field(default_factory=DeltaContent)
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming chunk. No vendor extensions."""
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "las-default"
    choices: List[ChatCompletionChunkChoice] = Field(default_factory=list)
