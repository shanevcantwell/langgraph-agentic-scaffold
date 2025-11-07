"""
MCP Client - Convenience wrapper for making MCP service calls.

Provides a simple interface for specialists to call other specialists'
functions without manually constructing McpRequest objects.
"""

from typing import Any
import logging

from .registry import McpRegistry
from .schemas import McpRequest, McpResponse

logger = logging.getLogger(__name__)


class McpClient:
    """
    Convenience wrapper for MCP invocation.

    Provides a simple interface for specialists to call other specialists'
    functions without manually constructing McpRequest objects.

    Example:
        # In a specialist's execute method
        if self.mcp_client:
            result = self.mcp_client.call(
                "file_specialist",
                "file_exists",
                path="/workspace/data.txt"
            )
            if result:
                # File exists, proceed with logic
                pass

    Design:
    - Automatic request serialization (kwargs → McpRequest)
    - Automatic response deserialization (McpResponse → data)
    - Raises exceptions on errors for clean error handling
    - Logs all calls at DEBUG level
    """

    def __init__(self, registry: McpRegistry):
        """
        Initialize MCP client with registry reference.

        Args:
            registry: The graph's McpRegistry instance
        """
        self.registry = registry
        logger.debug("Initialized McpClient")

    def call(self, service_name: str, function_name: str, **parameters) -> Any:
        """
        Synchronous MCP call with automatic serialization/deserialization.

        Args:
            service_name: Name of the service to invoke (e.g., "file_specialist")
            function_name: Name of the function to call (e.g., "file_exists")
            **parameters: Function arguments as keyword arguments

        Returns:
            The function's return value (deserialized from McpResponse.data)

        Raises:
            ValueError: If response status is "error"

        Example:
            # Check if file exists
            exists = client.call("file_specialist", "file_exists", path="/data.txt")

            # List files in directory
            files = client.call("file_specialist", "list_files", path="/workspace")

            # Read file contents
            content = client.call("file_specialist", "read_file", path="/data.txt")
        """
        # Build request
        request = McpRequest(
            service_name=service_name,
            function_name=function_name,
            parameters=parameters
        )

        logger.debug(
            f"McpClient.call: {service_name}.{function_name}() "
            f"[request_id={request.request_id}]"
        )

        # Dispatch via registry
        response = self.registry.dispatch(request)

        # Check for errors and raise if needed
        response.raise_for_error()

        # Return deserialized data
        return response.data

    def call_safe(self, service_name: str, function_name: str, **parameters) -> tuple[bool, Any]:
        """
        Safe MCP call that returns (success, result) instead of raising.

        Useful when you want to handle errors inline without try/except blocks.

        Args:
            service_name: Name of the service to invoke
            function_name: Name of the function to call
            **parameters: Function arguments as keyword arguments

        Returns:
            Tuple of (success: bool, result: Any)
            - On success: (True, function_return_value)
            - On error: (False, error_message)

        Example:
            success, result = client.call_safe(
                "file_specialist",
                "file_exists",
                path="/maybe_missing.txt"
            )
            if success:
                print(f"File exists: {result}")
            else:
                print(f"Error checking file: {result}")
        """
        try:
            result = self.call(service_name, function_name, **parameters)
            return (True, result)
        except ValueError as e:
            # MCP call failed (response.status == "error")
            error_msg = str(e).replace("MCP call failed: ", "")
            return (False, error_msg)
        except Exception as e:
            # Unexpected error
            logger.error(f"Unexpected error in McpClient.call_safe: {e}", exc_info=True)
            return (False, str(e))

    def list_services(self) -> dict:
        """
        Get list of all available MCP services and their functions.

        Returns:
            Dictionary mapping service_name -> list of function names

        Example:
            services = client.list_services()
            # {'file_specialist': ['file_exists', 'list_files', 'read_file'], ...}
        """
        return self.registry.list_services()
