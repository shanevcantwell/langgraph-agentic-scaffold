import logging
from typing import Dict, Any, Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)


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
    to FileSpecialist via MCP. It serves as the routable interface layer while
    FileSpecialist remains the MCP-only service layer.

    Architecture Pattern (aligns with ADR-MCP-002 Dockyard):
    - FileOperationsSpecialist: User interface layer (LLM-driven, routable)
    - FileSpecialist: Service layer (MCP-only, procedural)
    - Future: DockmasterSpecialist: Storage layer (uploaded files)

    Example Flow:
        User: "list files in workspace"
          ↓
        Router → FileOperationsSpecialist
          ↓
        FileOperationsSpecialist.mcp_client.call("file_specialist", "list_files")
          ↓
        Returns formatted response to user
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpret user's file operation request and execute via MCP.

        Uses LLM tool calling to parse user intent, then routes to appropriate
        FileSpecialist MCP function.
        """
        if not self.mcp_client:
            logger.error("FileOperationsSpecialist: MCP client not available")
            return {
                "messages": [AIMessage(content="Error: File operations service not available. Please contact administrator.")],
                "task_is_complete": True
            }

        # Use LLM to parse user intent
        messages = state.get("messages", [])
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

    def _execute_file_operation(self, operation: str, args: Dict[str, Any]) -> str:
        """
        Execute the specified file operation via MCP.

        Args:
            operation: Operation name (list_files, read_file, etc.)
            args: Operation arguments from LLM tool call

        Returns:
            Formatted result message for user
        """
        try:
            if operation == "list_files":
                path = args.get('path', '.')
                files = self.mcp_client.call(
                    "file_specialist",
                    "list_files",
                    path=path
                )
                if not files:
                    return f"No files found in '{path}'."
                files_list = '\n'.join(f"  - {f}" for f in files)
                return f"Files in '{path}':\n{files_list}"

            elif operation == "read_file":
                path = args.get('path')
                if not path:
                    return "Error: No file path specified."

                content = self.mcp_client.call(
                    "file_specialist",
                    "read_file",
                    path=path
                )
                return f"Contents of '{path}':\n```\n{content}\n```"

            elif operation == "write_file":
                path = args.get('path')
                content = args.get('content', '')

                if not path:
                    return "Error: No file path specified."

                result = self.mcp_client.call(
                    "file_specialist",
                    "write_file",
                    path=path,
                    content=content
                )
                return f"✓ {result}"

            elif operation == "append_to_file":
                path = args.get('path')
                content = args.get('content', '')

                if not path:
                    return "Error: No file path specified."

                result = self.mcp_client.call(
                    "file_specialist",
                    "append_to_file",
                    path=path,
                    content=content
                )
                return f"✓ {result}"

            elif operation == "create_directory":
                path = args.get('path')

                if not path:
                    return "Error: No directory path specified."

                result = self.mcp_client.call(
                    "file_specialist",
                    "create_directory",
                    path=path
                )
                return f"✓ {result}"

            elif operation == "delete_file":
                path = args.get('path')

                if not path:
                    return "Error: No file path specified."

                result = self.mcp_client.call(
                    "file_specialist",
                    "delete_file",
                    path=path
                )
                return f"✓ {result}"

            elif operation == "rename_file":
                old_path = args.get('old_path')
                new_path = args.get('new_path')

                if not old_path or not new_path:
                    return "Error: Both old and new paths required for rename."

                result = self.mcp_client.call(
                    "file_specialist",
                    "rename_file",
                    old_path=old_path,
                    new_path=new_path
                )
                return f"✓ {result}"

            else:
                return f"Error: Unknown operation '{operation}'"

        except Exception as e:
            logger.error(f"MCP call failed for {operation}: {e}")
            return f"Error executing {operation}: {str(e)}"
