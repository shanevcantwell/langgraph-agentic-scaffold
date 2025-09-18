# app/src/specialists/schemas/_archiver.py

from datetime import datetime
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from ._base import SpecialistOutput  # <-- Correct inheritance

class SuccessReport(BaseModel):
    """
    Defines the data structure for the final summary report. This is the
    'payload' of the archiver's output.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="The UTC timestamp of when the report was generated.")
    final_user_response: str = Field(..., description="The final response generated for the user.")
    routing_history: List[str] = Field(default_factory=list, description="A list of specialists that were invoked, in order.")
    artifacts: Dict[str, Any] = Field(default_factory=dict, description="A dictionary of any artifacts created during the run.")
    scratchpad: Dict[str, Any] = Field(default_factory=dict, description="A summary of the final state of the scratchpad.")
    conversation_summary: str = Field(..., description="A summary of the conversation history.")

class ArchiverSpecialistOutput(SpecialistOutput):
    """
    Defines the complete output object for the ArchiverSpecialist, adhering
    to the base data contract.
    """
    payload: SuccessReport