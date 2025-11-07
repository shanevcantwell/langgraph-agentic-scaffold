"""
MCP Protocol Schemas - Request/Response data structures for service invocation.
"""

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field
import uuid


class McpRequest(BaseModel):
    """
    Request for synchronous MCP service invocation.

    Examples:
        # Check if file exists
        McpRequest(
            service_name="file_specialist",
            function_name="file_exists",
            parameters={"path": "/workspace/data.txt"}
        )

        # List files in directory
        McpRequest(
            service_name="file_specialist",
            function_name="list_files",
            parameters={"path": "/workspace"}
        )
    """
    service_name: str = Field(
        ...,
        description="Name of the specialist service to invoke (e.g., 'file_specialist')"
    )
    function_name: str = Field(
        ...,
        description="Name of the function to call on the service"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Function arguments as key-value pairs"
    )
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for request tracing (auto-generated)"
    )


class McpResponse(BaseModel):
    """
    Response from MCP service invocation.

    Examples:
        # Success response
        McpResponse(
            status="success",
            data=True,
            request_id="abc-123"
        )

        # Error response
        McpResponse(
            status="error",
            error_message="File not found: /workspace/missing.txt",
            request_id="abc-123"
        )
    """
    status: Literal["success", "error"] = Field(
        ...,
        description="Execution status of the MCP call"
    )
    data: Optional[Any] = Field(
        None,
        description="Return value from the function (only present on success)"
    )
    error_message: Optional[str] = Field(
        None,
        description="Error details (only present on error)"
    )
    request_id: Optional[str] = Field(
        None,
        description="Echo of request_id for correlation"
    )

    def raise_for_error(self):
        """
        Convenience method to raise exception if response is an error.

        Raises:
            ValueError: If status is "error"
        """
        if self.status == "error":
            raise ValueError(f"MCP call failed: {self.error_message}")
