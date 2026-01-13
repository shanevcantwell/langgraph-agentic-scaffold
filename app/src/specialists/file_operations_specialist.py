import logging
from typing import Dict, Any, Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..mcp import sync_call_external_mcp

logger = logging.getLogger(__name__)


def _extract_text_from_mcp_result(result) -> str:
    """Extract text content from external MCP result object."""
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


class FileOperation(BaseModel):
    """Schema for file operation tool calling."""
    operation: Literal["list_files", "read_file", "write_file", "append_to_file",
                      "create_directory", "delete_file", "rename_file"] = Field(
        ...,
        description="The file operation to perform"
    )
    path: Optional[str] = Field(
        default=".",
        description="File or directory path (relative to workspace root). Use '.' for workspace root."
    )
    content: Optional[str] = Field(
        default=None,
        description="Content for write/append operations"
    )
    old_path: Optional[str] = Field(
        default=None,
        description="Old path for rename operations"
    )
    new_path: Optional[str] = Field(
        default=None,
        description="New path for rename operations"
    )


class FileOperationsSpecialist(BaseSpecialist):
    """
    User interface layer for file system operations.

    This specialist interprets user requests for file operations and routes them
    to the external filesystem MCP container (ADR-CORE-035).

    Architecture Pattern:
    - FileOperationsSpecialist: User interface layer (LLM-driven, routable)
    - Filesystem MCP: External container (@modelcontextprotocol/server-filesystem)

    Example Flow:
        User: "list files in workspace"
          ↓
        Router → FileOperationsSpecialist
          ↓
        sync_call_external_mcp("filesystem", "list_directory", ...)
          ↓
        Returns formatted response to user

    Note: external_mcp_client is injected by GraphBuilder after specialist loading.
    """

    def _is_filesystem_available(self) -> bool:
        """Check if external filesystem MCP is connected."""
        if not hasattr(self, 'external_mcp_client') or self.external_mcp_client is None:
            return False
        return self.external_mcp_client.is_connected("filesystem")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret user's file operation request and execute via external filesystem MCP.

        Uses LLM tool calling to parse user intent, then routes to appropriate
        filesystem MCP function.
        """
        if not self._is_filesystem_available():
            logger.error("FileOperationsSpecialist: Filesystem MCP not available")
            return {
                "messages": [AIMessage(content="Error: File operations service not available. The filesystem container may not be running.")],
                "task_is_complete": True
            }

        # Use LLM to parse user intent
        messages = self._get_enriched_messages(state)
        if not messages:
            return {
                "messages": [AIMessage(content="Error: No user request to process.")],
                "task_is_complete": True
            }

        try:
            # Call LLM with FileOperation tool
            request = StandardizedLLMRequest(
                messages=messages,
                tools=[FileOperation],
                force_tool_call=True
            )

            response = self.llm_adapter.invoke(request)
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                return {
                    "messages": [AIMessage(content="I couldn't determine what file operation you want to perform. Please be more specific (e.g., 'list files', 'create test.txt', 'read config.json').")],
                    "task_is_complete": True
                }

            # Extract operation details
            operation_args = tool_calls[0]['args']
            operation = operation_args['operation']

            logger.info(f"FileOperationsSpecialist: Executing {operation} via MCP")

            # Route to appropriate MCP function
            result = self._execute_file_operation(operation, operation_args)

            return {
                "messages": [AIMessage(content=result)],
                "task_is_complete": True
            }

        except Exception as e:
            logger.error(f"FileOperationsSpecialist error: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content=f"Error performing file operation: {str(e)}")],
                "task_is_complete": True
            }

    def _call_filesystem_mcp(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Call external filesystem MCP and extract text result.

        Args:
            tool_name: Filesystem MCP tool name
            arguments: Tool arguments

        Returns:
            Text content from MCP result
        """
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "filesystem",
            tool_name,
            arguments
        )
        return _extract_text_from_mcp_result(result)

    def _execute_file_operation(self, operation: str, args: Dict[str, Any]) -> str:
        """
        Execute the specified file operation via external filesystem MCP.

        Args:
            operation: Operation name (list_files, read_file, etc.)
            args: Operation arguments from LLM tool call

        Returns:
            Formatted result message for user

        Tool mapping (internal → filesystem MCP):
            list_files → list_directory
            read_file → read_file
            write_file → write_file
            append_to_file → (read + append + write)
            create_directory → create_directory
            delete_file → (not supported in filesystem MCP)
            rename_file → move_file
        """
        try:
            if operation == "list_files":
                path = args.get('path', '.')
                result = self._call_filesystem_mcp("list_directory", {"path": path})

                # Parse directory listing
                if not result or result.strip() == "":
                    return f"No files found in '{path}'."

                # Try to parse as structured output, fall back to raw
                lines = [line.strip() for line in result.split('\n') if line.strip()]
                if not lines:
                    return f"No files found in '{path}'."

                files_list = '\n'.join(f"  - {f}" for f in lines)
                return f"Files in '{path}':\n{files_list}"

            elif operation == "read_file":
                path = args.get('path')
                if not path:
                    return "Error: No file path specified."

                content = self._call_filesystem_mcp("read_file", {"path": path})
                return f"Contents of '{path}':\n```\n{content}\n```"

            elif operation == "write_file":
                path = args.get('path')
                content = args.get('content', '')

                if not path:
                    return "Error: No file path specified."

                result = self._call_filesystem_mcp("write_file", {
                    "path": path,
                    "content": content
                })
                return f"✓ Successfully wrote to '{path}'"

            elif operation == "append_to_file":
                path = args.get('path')
                content = args.get('content', '')

                if not path:
                    return "Error: No file path specified."

                # Filesystem MCP doesn't have append - read existing, append, write
                try:
                    existing = self._call_filesystem_mcp("read_file", {"path": path})
                except Exception:
                    existing = ""  # File may not exist yet

                new_content = existing + content
                self._call_filesystem_mcp("write_file", {
                    "path": path,
                    "content": new_content
                })
                return f"✓ Successfully appended to '{path}'"

            elif operation == "create_directory":
                path = args.get('path')

                if not path:
                    return "Error: No directory path specified."

                result = self._call_filesystem_mcp("create_directory", {"path": path})
                return f"✓ Successfully created directory '{path}'"

            elif operation == "delete_file":
                path = args.get('path')

                if not path:
                    return "Error: No file path specified."

                # Note: Filesystem MCP may not support delete
                # Try move_file to a .deleted location as workaround, or report unsupported
                return f"Error: Delete operation is not supported by the filesystem service. Consider using move_file to relocate the file instead."

            elif operation == "rename_file":
                old_path = args.get('old_path')
                new_path = args.get('new_path')

                if not old_path or not new_path:
                    return "Error: Both old and new paths required for rename."

                result = self._call_filesystem_mcp("move_file", {
                    "source": old_path,
                    "destination": new_path
                })
                return f"✓ Successfully renamed '{old_path}' to '{new_path}'"

            else:
                return f"Error: Unknown operation '{operation}'"

        except Exception as e:
            logger.error(f"Filesystem MCP call failed for {operation}: {e}")
            return f"Error executing {operation}: {str(e)}"
