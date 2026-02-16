"""
Message-Centric Protocol (MCP) - Service invocation between specialists.

MCP enables specialists to call services directly without routing through the graph.
This reduces latency and LLM costs for deterministic operations.

Internal MCP (Python):
- McpRequest/McpResponse: Pydantic schemas for service invocation
- McpRegistry: Per-graph-instance registry of available services
- McpClient: Convenience wrapper for making MCP calls

External MCP (Containers):
- ExternalMcpClient: Async client for external MCP servers (Node.js, Docker)
- sync_call_external_mcp: Sync bridge for calling external MCP from sync code

Design Decisions:
- Internal MCP: Synchronous Python function calls
- External MCP: Async JSON-RPC via stdio (ADR-MCP-003)
- Per-graph-instance registry (not singleton) for test isolation
- LangSmith tracing with configuration toggle
- 5-second timeout for internal MCP calls
"""

from .schemas import McpRequest, McpResponse
from .registry import McpRegistry
from .client import McpClient
from .external_client import ExternalMcpClient, sync_call_external_mcp
from .permissioned_client import PermissionedMcpClient
from .utils import extract_text_from_mcp_result
from .react_step import (
    ToolDef,
    is_react_available,
    call_react_step,
    parse_react_step_result,
    build_tool_schemas,
    dispatch_external_tool,
)
from .artifact_tools import (
    list_artifacts,
    retrieve_artifact,
    format_artifact_value,
    artifact_tool_defs,
    dispatch_artifact_tool,
    ARTIFACT_TOOL_PARAMS,
)

__all__ = [
    "McpRequest",
    "McpResponse",
    "McpRegistry",
    "McpClient",
    "ExternalMcpClient",
    "PermissionedMcpClient",
    "sync_call_external_mcp",
    "extract_text_from_mcp_result",
    # react_step helpers (#162)
    "ToolDef",
    "is_react_available",
    "call_react_step",
    "parse_react_step_result",
    "build_tool_schemas",
    "dispatch_external_tool",
    # Artifact inspection tools (#195)
    "list_artifacts",
    "retrieve_artifact",
    "format_artifact_value",
    "artifact_tool_defs",
    "dispatch_artifact_tool",
    "ARTIFACT_TOOL_PARAMS",
]
