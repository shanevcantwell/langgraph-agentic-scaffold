# app/src/executors/__init__.py
"""
Executors - procedural dispatch layer for operation lists.

Pattern (ADR-CORE-049):
    Specialist (LLM) → list[Operation] → Executor → Backend (MCP, etc.)

The executor handles "how" (dispatch, error handling, iteration).
Specialists handle "what" (LLM inference produces operation lists).
"""
from .file_operation_executor import FileOperationExecutor, OperationResult

__all__ = ["FileOperationExecutor", "OperationResult"]
