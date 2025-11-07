"""
Message-Centric Protocol (MCP) - Synchronous service invocation between specialists.

MCP enables specialists to call each other's functions directly without routing through
the graph. This reduces latency and LLM costs for deterministic operations.

Key Components:
- McpRequest/McpResponse: Pydantic schemas for service invocation
- McpRegistry: Per-graph-instance registry of available services
- McpClient: Convenience wrapper for making MCP calls

Design Decisions:
- Synchronous-only (async can be added later if needed)
- Per-graph-instance registry (not singleton) for test isolation
- LangSmith tracing with configuration toggle
- 5-second timeout for safety
"""

from .schemas import McpRequest, McpResponse
from .registry import McpRegistry
from .client import McpClient

__all__ = [
    "McpRequest",
    "McpResponse",
    "McpRegistry",
    "McpClient",
]
