# app/src/specialists/mixins/__init__.py
"""
Specialist mixins for optional capabilities.

Mixins provide orthogonal capabilities that specialists can opt into:
- ReActMixin: Iterative tool use (LLM → tool → LLM → tool → ... → done)
"""

from .react_mixin import (
    ReActMixin,
    ToolDef,
    ToolCall,
    ToolResult,
    ReActIteration,  # ADR-CORE-055: Trace record type
    ReActLoopTerminated,
    MaxIterationsExceeded,
    StagnationDetected,
    ToolExecutionError,
)

__all__ = [
    "ReActMixin",
    "ToolDef",
    "ToolCall",
    "ToolResult",
    "ReActIteration",  # ADR-CORE-055: Trace record type
    "ReActLoopTerminated",
    "MaxIterationsExceeded",
    "StagnationDetected",
    "ToolExecutionError",
]
