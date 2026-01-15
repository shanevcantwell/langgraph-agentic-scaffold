# app/src/dispatchers/file_operation_dispatcher.py
"""
FileOperationDispatcher - dispatches file operations to MCP (ADR-CORE-049).

This dispatcher handles "how" - the procedural dispatch of operations to
the filesystem MCP backend. Specialists handle "what" via LLM inference.

Pattern:
    Specialist (LLM) → list[FileOperation] → FileOperationDispatcher → MCP

Usage:
    operations = [
        FileOperation(type="write", path="e.txt", content=""),
        FileOperation(type="move", path="old.txt", destination="new/old.txt"),
    ]

    dispatcher = FileOperationDispatcher(external_mcp_client)
    results = await dispatcher.dispatch(operations)
    # Or sync: results = dispatcher.dispatch_sync(operations)
"""
import logging
from dataclasses import dataclass
from typing import List, Optional, Any, TYPE_CHECKING

from .base import BaseDispatcher
from ..mcp import extract_text_from_mcp_result

if TYPE_CHECKING:
    from ..mcp.external_client import ExternalMcpClient
    from ..specialists.schemas._file_operations import FileOperation

logger = logging.getLogger(__name__)


def _normalize_path(path: str) -> str:
    """
    Normalize path for filesystem MCP (must be relative to /app mount).

    Strips leading slashes since filesystem MCP expects relative paths.
    """
    if path.startswith("/"):
        original = path
        path = path.lstrip("/")
        logger.warning(f"Normalized path: '{original}' → '{path}' (stripped leading slash)")
    return path


@dataclass
class OperationResult:
    """Result of executing a single file operation."""
    operation: "FileOperation"
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None

    def __repr__(self) -> str:
        status = "OK" if self.success else f"FAIL: {self.error}"
        return f"OperationResult({self.operation.type} {self.operation.path}: {status})"


class FileOperationDispatcher(BaseDispatcher["FileOperation", OperationResult]):
    """
    Dispatches file operations to filesystem MCP.

    Inherits from BaseDispatcher which provides:
    - dispatch(): Async generator yielding results
    - dispatch_sync(): Sync wrapper for specialist code

    This class implements:
    - _dispatch_one(): Match/case dispatch to MCP tools
    - _make_error_result(): Error result factory

    Args:
        mcp_client: ExternalMcpClient instance with filesystem connection
        service_name: MCP service name (default "filesystem")
    """

    def __init__(
        self,
        mcp_client: "ExternalMcpClient",
        service_name: str = "filesystem"
    ):
        super().__init__(mcp_client, service_name)
        # Alias for clarity (backend_client is the generic name)
        self.mcp_client = mcp_client

    async def _dispatch_one(self, op: "FileOperation") -> OperationResult:
        """Dispatch single file operation to MCP."""
        # Normalize paths (strip leading slashes for filesystem MCP)
        path = _normalize_path(op.path)
        destination = _normalize_path(op.destination) if op.destination else None

        try:
            match op.type:
                case "write":
                    await self.mcp_client.call_tool(
                        self.service_name,
                        "write_file",
                        {"path": path, "content": op.content or ""}
                    )
                    return OperationResult(op, success=True, result=f"Created {path}")

                case "move":
                    if not destination:
                        return OperationResult(
                            op, success=False, error="Move requires destination"
                        )
                    await self.mcp_client.call_tool(
                        self.service_name,
                        "move_file",
                        {"source": path, "destination": destination}
                    )
                    return OperationResult(op, success=True, result=f"Moved to {op.destination}")

                case "mkdir":
                    await self.mcp_client.call_tool(
                        self.service_name,
                        "create_directory",
                        {"path": path}
                    )
                    return OperationResult(op, success=True, result=f"Created directory {path}")

                case "list":
                    listing = await self.mcp_client.call_tool(
                        self.service_name,
                        "list_directory",
                        {"path": path}
                    )
                    text = extract_text_from_mcp_result(listing)
                    return OperationResult(op, success=True, result=text)

                case "read":
                    content = await self.mcp_client.call_tool(
                        self.service_name,
                        "read_file",
                        {"path": path}
                    )
                    text = extract_text_from_mcp_result(content)
                    return OperationResult(op, success=True, result=text)

                case "delete":
                    # filesystem MCP may not support delete
                    return OperationResult(
                        op, success=False, error="Delete not supported by filesystem MCP"
                    )

                case _:
                    return OperationResult(
                        op, success=False, error=f"Unknown operation type: {op.type}"
                    )

        except Exception as e:
            logger.warning(f"Operation failed: {op.type} {op.path}: {e}")
            return OperationResult(op, success=False, error=str(e))

    def _make_error_result(self, op: "FileOperation", error: str) -> OperationResult:
        """Create error result for failed file operation."""
        return OperationResult(op, success=False, error=error)


# Backwards compatibility aliases
FileOperationExecutor = FileOperationDispatcher
