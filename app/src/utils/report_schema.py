# app/src/utils/report_schema.py
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import datetime

class ErrorReport(BaseModel):
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    error_message: str
    traceback: str
    routing_history: List[str]
    pruned_state: Dict[str, Any]