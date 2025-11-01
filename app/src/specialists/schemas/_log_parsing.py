# app/src/specialists/schemas/_log_parsing.py

from pydantic import BaseModel, Field
from typing import List, Optional

class ParsedTurn(BaseModel):
    sequence_id: int = Field(..., description="The sequence number of the turn.")
    datetime: str = Field(..., description="The ISO datetime of the turn.")
    prompt: str = Field(..., description="The full text of the user prompt.")
    response: str = Field(..., description="The full text of the AI response.")

class ParsedConversation(BaseModel):
    conversation_id: int
    datetime: str
    model_name: str
    description: Optional[str] = None
    turns: List[ParsedTurn]