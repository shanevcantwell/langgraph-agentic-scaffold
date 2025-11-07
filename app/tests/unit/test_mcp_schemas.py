"""
Unit tests for MCP protocol schemas (McpRequest, McpResponse).

Tests validate Pydantic schema parsing, validation, and error handling.
"""

import pytest
from pydantic import ValidationError

from app.src.mcp.schemas import McpRequest, McpResponse


class TestMcpRequest:
    """Test suite for McpRequest schema validation."""

    def test_valid_request_with_all_fields(self):
        """Test that a fully specified request is valid."""
        request = McpRequest(
            service_name="file_specialist",
            function_name="file_exists",
            parameters={"path": "/workspace/data.txt"},
            request_id="test-123"
        )

        assert request.service_name == "file_specialist"
        assert request.function_name == "file_exists"
        assert request.parameters == {"path": "/workspace/data.txt"}
        assert request.request_id == "test-123"

    def test_valid_request_minimal_fields(self):
        """Test that request is valid with only required fields."""
        request = McpRequest(
            service_name="file_specialist",
            function_name="list_files"
        )

        assert request.service_name == "file_specialist"
        assert request.function_name == "list_files"
        assert request.parameters == {}  # Default empty dict
        assert request.request_id is not None  # Auto-generated UUID

    def test_request_auto_generates_uuid(self):
        """Test that request_id is auto-generated when not provided."""
        request1 = McpRequest(service_name="test", function_name="fn")
        request2 = McpRequest(service_name="test", function_name="fn")

        # Both should have request_ids
        assert request1.request_id is not None
        assert request2.request_id is not None
        # They should be unique
        assert request1.request_id != request2.request_id

    def test_request_with_nested_parameters(self):
        """Test that parameters can contain nested structures."""
        request = McpRequest(
            service_name="complex_service",
            function_name="process",
            parameters={
                "nested": {
                    "data": [1, 2, 3],
                    "meta": {"key": "value"}
                }
            }
        )

        assert request.parameters["nested"]["data"] == [1, 2, 3]
        assert request.parameters["nested"]["meta"]["key"] == "value"

    def test_request_missing_service_name_fails(self):
        """Test that request without service_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            McpRequest(function_name="test")

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("service_name",) for error in errors)

    def test_request_missing_function_name_fails(self):
        """Test that request without function_name raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            McpRequest(service_name="test")

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("function_name",) for error in errors)

    def test_request_empty_strings_are_valid(self):
        """Test that empty strings are technically valid (registry will reject)."""
        # Pydantic allows empty strings - business logic validation happens in registry
        request = McpRequest(service_name="", function_name="")

        assert request.service_name == ""
        assert request.function_name == ""


class TestMcpResponse:
    """Test suite for McpResponse schema validation."""

    def test_valid_success_response(self):
        """Test that a success response with data is valid."""
        response = McpResponse(
            status="success",
            data={"result": True},
            request_id="test-123"
        )

        assert response.status == "success"
        assert response.data == {"result": True}
        assert response.error_message is None
        assert response.request_id == "test-123"

    def test_valid_error_response(self):
        """Test that an error response with error_message is valid."""
        response = McpResponse(
            status="error",
            error_message="File not found: /missing.txt",
            request_id="test-123"
        )

        assert response.status == "error"
        assert response.data is None
        assert response.error_message == "File not found: /missing.txt"
        assert response.request_id == "test-123"

    def test_response_minimal_fields(self):
        """Test that response is valid with only status field."""
        response = McpResponse(status="success")

        assert response.status == "success"
        assert response.data is None
        assert response.error_message is None
        assert response.request_id is None

    def test_response_data_can_be_any_type(self):
        """Test that data field accepts various data types."""
        # Boolean
        response1 = McpResponse(status="success", data=True)
        assert response1.data is True

        # String
        response2 = McpResponse(status="success", data="text")
        assert response2.data == "text"

        # List
        response3 = McpResponse(status="success", data=[1, 2, 3])
        assert response3.data == [1, 2, 3]

        # Dict
        response4 = McpResponse(status="success", data={"key": "value"})
        assert response4.data == {"key": "value"}

        # None
        response5 = McpResponse(status="success", data=None)
        assert response5.data is None

    def test_response_invalid_status_fails(self):
        """Test that invalid status value raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            McpResponse(status="pending")  # Only "success" or "error" allowed

        errors = exc_info.value.errors()
        assert any(
            "status" in str(error["loc"]) and "literal" in error["type"].lower()
            for error in errors
        )

    def test_response_missing_status_fails(self):
        """Test that response without status raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            McpResponse()

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("status",) for error in errors)

    def test_raise_for_error_with_success_status(self):
        """Test that raise_for_error does nothing for success responses."""
        response = McpResponse(status="success", data=42)

        # Should not raise
        response.raise_for_error()

    def test_raise_for_error_with_error_status(self):
        """Test that raise_for_error raises ValueError for error responses."""
        response = McpResponse(
            status="error",
            error_message="Something went wrong"
        )

        with pytest.raises(ValueError) as exc_info:
            response.raise_for_error()

        assert "MCP call failed" in str(exc_info.value)
        assert "Something went wrong" in str(exc_info.value)

    def test_response_can_have_both_data_and_error(self):
        """Test that response can technically have both (though semantically odd)."""
        # Pydantic allows this - application logic determines what to use
        response = McpResponse(
            status="error",
            data="some data",
            error_message="some error"
        )

        assert response.data == "some data"
        assert response.error_message == "some error"


class TestMcpSchemaIntegration:
    """Integration tests for request/response flow."""

    def test_request_response_id_correlation(self):
        """Test that request_id can be echoed in response for tracing."""
        request = McpRequest(
            service_name="test",
            function_name="fn",
            request_id="trace-123"
        )

        # Simulate service execution
        response = McpResponse(
            status="success",
            data="result",
            request_id=request.request_id
        )

        assert request.request_id == response.request_id == "trace-123"

    def test_empty_parameters_dict_is_valid(self):
        """Test that empty parameters dict works (for parameterless functions)."""
        request = McpRequest(
            service_name="service",
            function_name="get_timestamp",
            parameters={}
        )

        assert request.parameters == {}
