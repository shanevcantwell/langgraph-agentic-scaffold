"""
Schemas for BatchProcessorSpecialist operations.

Defines Pydantic models for batch file sorting with emergent LLM-driven logic.
"""
from typing import List, Literal, Union
from pydantic import BaseModel, Field, field_validator


class FileSortStrategy(BaseModel):
    """Strategy configuration for file sorting."""
    strategy: Literal["alphabetic", "emergent", "auto"] = Field(
        default="emergent",
        description="Sorting strategy: 'alphabetic' (predefined rules) or 'emergent' (LLM decides)"
    )
    read_content: bool = Field(
        default=False,
        description="Whether to read file contents for better decisions (slower)"
    )


class BatchSortRequest(BaseModel):
    """User's batch file sorting request (parsed by LLM)."""
    file_paths: List[str] = Field(
        ...,
        description="List of file paths to sort (relative to workspace root)",
        min_length=1
    )
    destination_directories: List[str] = Field(
        default_factory=list,
        description="Target directories for sorting (e.g., ['a-m/', 'n-z/']). If empty, LLM will infer from context."
    )
    strategy: Union[FileSortStrategy, str] = Field(
        default_factory=FileSortStrategy,
        description="Sorting strategy configuration"
    )

    @field_validator('strategy', mode='before')
    @classmethod
    def coerce_strategy(cls, v):
        """Convert string strategy to FileSortStrategy object."""
        if isinstance(v, str):
            # LLM might return just "auto" or "emergent" string
            strategy_name = v if v in ("alphabetic", "emergent", "auto") else "emergent"
            return FileSortStrategy(strategy=strategy_name)
        if isinstance(v, dict):
            return FileSortStrategy(**v)
        return v


class FileSortDecision(BaseModel):
    """LLM's decision for a single file."""
    file_path: str = Field(..., description="File being sorted")
    destination: str = Field(..., description="Target directory")
    rationale: str = Field(..., description="Why this file goes to this destination")


class BatchSortPlan(BaseModel):
    """Complete sorting plan from LLM."""
    decisions: List[FileSortDecision] = Field(
        ...,
        description="Sorting decisions for each file",
        min_length=1
    )
