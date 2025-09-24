# app/src/specialists/schemas/_base.py
from enum import Enum
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

class StatusEnum(str, Enum):
    """An enumeration for the status of a specialist's operation."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILURE = "FAILURE"
    PENDING = "PENDING"
    SELF_CORRECTING = "SELF_CORRECTING"

class SpecialistOutput(BaseModel, Generic[T]):
    """
    A standardized response envelope for all LLM-driven specialist outputs.
    This provides a consistent structure for reporting status, rationale,
    and the actual data payload.
    """
    status: StatusEnum = Field(
        ...,
        description="The machine-readable status of the operation."
    )
    rationale: str = Field(
        ...,
        description="A brief, human-readable explanation of the reasoning behind the status and payload, or notes on any deviations."
    )
    payload: Optional[T] = Field(
        default=None,
        description="The specific data payload, such as WebContent or a Critique. Can be null in case of total failure."
    )
    