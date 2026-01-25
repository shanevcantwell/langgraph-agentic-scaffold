# app/src/specialists/schemas/_file_operations.py
"""
Operation schemas for file operations (ADR-CORE-049).

These schemas represent the "what" - output of LLM inference.
The FileOperationExecutor handles the "how" - dispatch to MCP.

Pattern:
    Specialist (LLM) → list[FileOperation] → Executor → MCP
"""
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class FileOperation(BaseModel):
    """
    Typed file operation - output of LLM inference.

    This is the universal schema for all file operations. The executor
    dispatches based on the `type` field.

    Examples:
        FileOperation(type="write", path="e.txt", content="")
        FileOperation(type="move", path="old.txt", destination="new.txt")
        FileOperation(type="mkdir", path="archive/")
        FileOperation(type="list", path="/workspace")
    """
    type: Literal["read", "write", "move", "delete", "mkdir", "list"] = Field(
        ...,
        description="Operation type: read, write, move, delete, mkdir, or list"
    )
    path: str = Field(
        ...,
        description="Primary path for the operation (source for move, target for others)"
    )
    content: Optional[str] = Field(
        default=None,
        description="Content for write operations"
    )
    destination: Optional[str] = Field(
        default=None,
        description="Full destination path including filename for move operations (e.g., 'archive/file.txt' not 'archive/')"
    )


class FileOperationList(BaseModel):
    """
    List of file operations produced by LLM inference.

    Used as the output schema for structured LLM calls that parse
    user intent into executable operations.
    """
    operations: List[FileOperation] = Field(
        ...,
        description="List of file operations to execute"
    )
    rationale: Optional[str] = Field(
        default=None,
        description="LLM's reasoning for these operations (optional)"
    )
