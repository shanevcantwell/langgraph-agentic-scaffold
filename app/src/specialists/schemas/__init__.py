# app/src/specialists/schemas/__init__.py

"""
This package defines the Pydantic models that serve as the data contracts
for specialist inputs and outputs. By organizing schemas into domain-specific
files, we improve discoverability and maintainability.

The __init__.py file re-exports all schemas from their respective modules,
allowing for a single, clean import path for consumers, like:
from app.src.specialists.schemas import WebContent, ReadFileParams
"""

from ._base import SpecialistOutput, StatusEnum
from ._data import AnalysisResult, ExtractedData, Sentiment, CodeExecutionParams
from ._file_ops import (
    BaseFileParams,
    ListDirectoryParams,
    ReadFileParams,
    WriteFileParams,
)
from ._orchestration import Critique, SystemPlan, TriageRecommendations
from ._web import WebContent

__all__ = [
    "SpecialistOutput", "StatusEnum",
    "AnalysisResult", "ExtractedData", "Sentiment", "CodeExecutionParams",
    "BaseFileParams", "ListDirectoryParams", "ReadFileParams", "WriteFileParams",
    "Critique", "SystemPlan", "TriageRecommendations",
    "WebContent",
]
