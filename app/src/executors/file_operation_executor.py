# app/src/executors/file_operation_executor.py
"""
FileOperationExecutor - dispatches file operations to MCP (ADR-CORE-049).

This executor handles "how" - the procedural dispatch of operations to
the filesystem MCP backend. Specialists handle "what" via LLM inference.

Pattern:
    Specialist (LLM) → list[FileOperation] → FileOperationExecutor → MCP

Design notes (for research alignment, ADR-CORE-030):
    - Takes list, yields results (async generator)
    - Handles errors per-operation (doesn't abort batch)
    - Same pattern applies to DroneDispatcher for research tasks
    - Difference: research drones have ReAct loops inside, file ops are direct

Usage:
    operations = [
        FileOperation(type="write", path="e.txt", content=""),
        FileOperation(type="move", path="old.txt", destination="new/old.txt"),
    ]

    executor = FileOperationExecutor(external_mcp_client)
    results = await executor.execute(operations)
    # Or sync: results = executor.execute_sync(operations)
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional, Any, TYPE_CHECKING

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


def _extract_text_from_mcp_result(result: Any) -> str:
    """Extract text content from MCP result object."""
    if result is None:
        return ""

    if hasattr(result, 'content'):
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            first = content[0]
            if hasattr(first, 'text'):
                return first.text
            return str(first)
        return str(content)

    return str(result)


class FileOperationExecutor:
    """
    Async executor - dispatches file operations to filesystem MCP.

    The executor is async-native (per ADR-CORE-014), but provides
    execute_sync() for use in sync specialist code.

    Args:
        mcp_client: ExternalMcpClient instance with filesystem connection
        service_name: MCP service name (default "filesystem")
    """

    def __init__(
        self,
        mcp_client: "ExternalMcpClient",
        service_name: str = "filesystem"
    ):
        self.mcp_client = mcp_client
        self.service_name = service_name

    async def execute(
        self,
        operations: List["FileOperation"]
    ) -> AsyncGenerator[OperationResult, None]:
        """
        Execute operations, yielding results as they complete.

        Args:
            operations: List of FileOperation objects

        Yields:
            OperationResult for each operation
        """
        logger.info(f"FileOperationExecutor: executing {len(operations)} operations")

        for i, op in enumerate(operations, 1):
            logger.debug(f"Operation {i}/{len(operations)}: {op.type} {op.path}")
            result = await self._dispatch(op)
            yield result

    async def _dispatch(self, op: "FileOperation") -> OperationResult:
        """Dispatch single operation to MCP."""
        from ..specialists.schemas._file_operations import FileOperation

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
                    text = _extract_text_from_mcp_result(listing)
                    return OperationResult(op, success=True, result=text)

                case "read":
                    content = await self.mcp_client.call_tool(
                        self.service_name,
                        "read_file",
                        {"path": path}
                    )
                    text = _extract_text_from_mcp_result(content)
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

    def execute_sync(
        self,
        operations: List["FileOperation"],
        timeout: float = 60.0
    ) -> List[OperationResult]:
        """
        Sync wrapper for execute() - for use in sync specialist code.

        Uses run_coroutine_threadsafe to schedule on main event loop
        (same pattern as sync_call_external_mcp, see GitHub #28).

        Args:
            operations: List of FileOperation objects
            timeout: Seconds to wait for all operations

        Returns:
            List of OperationResult objects

        Raises:
            RuntimeError: If event loop not available or timeout
        """
        import concurrent.futures

        if self.mcp_client._main_loop is None:
            raise RuntimeError(
                "MCP client not initialized. "
                "Call connect_all_from_config() first."
            )

        async def collect_results() -> List[OperationResult]:
            results = []
            async for result in self.execute(operations):
                results.append(result)
            return results

        logger.debug(f"execute_sync: scheduling {len(operations)} ops on main loop")

        future = asyncio.run_coroutine_threadsafe(
            collect_results(),
            self.mcp_client._main_loop
        )

        try:
            results = future.result(timeout=timeout)
            logger.info(
                f"execute_sync: completed {len(results)} ops, "
                f"{sum(1 for r in results if r.success)} succeeded"
            )
            return results
        except concurrent.futures.TimeoutError:
            raise RuntimeError(
                f"FileOperationExecutor timed out after {timeout}s "
                f"with {len(operations)} operations"
            )
