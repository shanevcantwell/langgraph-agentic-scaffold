# app/src/dispatchers/__init__.py
"""
Dispatchers - procedural dispatch layer for operation lists.

Pattern (ADR-CORE-049):
    Specialist (LLM) → list[Operation] → Dispatcher → Backend (MCP, etc.)

The dispatcher handles "how" (dispatch, error handling, iteration).
Specialists handle "what" (LLM inference produces operation lists).

Available dispatchers:
    - FileOperationDispatcher: Filesystem MCP operations
    - DroneDispatcher (future): Research drone dispatch

Base class:
    - BaseDispatcher: ABC for creating new dispatchers
"""
from .base import BaseDispatcher
from .file_operation_dispatcher import (
    FileOperationDispatcher,
    FileOperationExecutor,  # backwards compat alias
    OperationResult,
)

__all__ = [
    "BaseDispatcher",
    "FileOperationDispatcher",
    "FileOperationExecutor",  # backwards compat alias
    "OperationResult",
]
