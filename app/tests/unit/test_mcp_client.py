"""
Unit tests for McpClient - Convenience wrapper for MCP service calls.

Tests validate client initialization, call methods, error handling,
and integration with McpRegistry.
"""

import pytest
from unittest.mock import Mock, MagicMock

from app.src.mcp.client import McpClient
from app.src.mcp.registry import McpRegistry
from app.src.mcp.schemas import McpRequest, McpResponse


class TestMcpClientInitialization:
    """Test suite for McpClient initialization."""

    def test_client_initializes_with_registry(self):
        """Test that client requires and stores registry reference."""
        registry = Mock(spec=McpRegistry)
        client = McpClient(registry)

        assert client.registry is registry

    def test_client_can_access_registry_methods(self):
        """Test that client can access registry services."""
        registry = McpRegistry({})
        registry.register_service("test_service", {"func": lambda: "ok"})

        client = McpClient(registry)

        services = client.list_services()
        assert "test_service" in services


class TestMcpClientCall:
    """Test suite for McpClient.call() method."""

    def test_call_success_returns_data(self):
        """Test that successful call returns deserialized data."""
        registry = McpRegistry({})

        def add_numbers(a, b):
            return a + b

        registry.register_service("math", {"add": add_numbers})
        client = McpClient(registry)

        result = client.call("math", "add", a=10, b=5)

        assert result == 15

    def test_call_with_no_parameters(self):
        """Test call with function that takes no parameters."""
        registry = McpRegistry({})

        def get_constant():
            return 42

        registry.register_service("constants", {"answer": get_constant})
        client = McpClient(registry)

        result = client.call("constants", "answer")

        assert result == 42

    def test_call_with_complex_return_value(self):
        """Test call that returns nested data structures."""
        registry = McpRegistry({})

        def get_user(user_id):
            return {
                "id": user_id,
                "name": "Alice",
                "permissions": ["read", "write"]
            }

        registry.register_service("users", {"get": get_user})
        client = McpClient(registry)

        result = client.call("users", "get", user_id=123)

        assert result["id"] == 123
        assert result["name"] == "Alice"
        assert "write" in result["permissions"]

    def test_call_raises_on_service_not_found(self):
        """Test that call raises ValueError for nonexistent service."""
        registry = McpRegistry({})
        client = McpClient(registry)

        with pytest.raises(ValueError) as exc_info:
            client.call("nonexistent_service", "some_func")

        assert "MCP call failed" in str(exc_info.value)
        assert "Service 'nonexistent_service' not found" in str(exc_info.value)

    def test_call_raises_on_function_not_found(self):
        """Test that call raises ValueError for nonexistent function."""
        registry = McpRegistry({})
        registry.register_service("test", {"valid_func": lambda: "ok"})
        client = McpClient(registry)

        with pytest.raises(ValueError) as exc_info:
            client.call("test", "invalid_func")

        assert "MCP call failed" in str(exc_info.value)
        assert "Function 'invalid_func' not found" in str(exc_info.value)

    def test_call_raises_on_function_execution_error(self):
        """Test that call raises ValueError when function fails."""
        registry = McpRegistry({})

        def failing_func():
            raise RuntimeError("Database connection failed")

        registry.register_service("db", {"query": failing_func})
        client = McpClient(registry)

        with pytest.raises(ValueError) as exc_info:
            client.call("db", "query")

        assert "MCP call failed" in str(exc_info.value)
        assert "Database connection failed" in str(exc_info.value)

    def test_call_constructs_request_correctly(self):
        """Test that call builds McpRequest with correct parameters."""
        registry = Mock(spec=McpRegistry)

        # Mock dispatch to return success response
        response = McpResponse(status="success", data="result")
        registry.dispatch.return_value = response

        client = McpClient(registry)
        result = client.call("service", "func", param1="value1", param2="value2")

        # Verify dispatch was called
        assert registry.dispatch.called
        request = registry.dispatch.call_args[0][0]

        # Verify request structure
        assert isinstance(request, McpRequest)
        assert request.service_name == "service"
        assert request.function_name == "func"
        assert request.parameters == {"param1": "value1", "param2": "value2"}
        assert request.request_id is not None  # Auto-generated

    def test_call_returns_none_when_function_returns_none(self):
        """Test that call correctly returns None values."""
        registry = McpRegistry({})

        def returns_none():
            return None

        registry.register_service("test", {"none_func": returns_none})
        client = McpClient(registry)

        result = client.call("test", "none_func")

        assert result is None


class TestMcpClientCallSafe:
    """Test suite for McpClient.call_safe() method."""

    def test_call_safe_success_returns_tuple(self):
        """Test that call_safe returns (True, result) on success."""
        registry = McpRegistry({})

        def multiply(x, y):
            return x * y

        registry.register_service("math", {"multiply": multiply})
        client = McpClient(registry)

        success, result = client.call_safe("math", "multiply", x=6, y=7)

        assert success is True
        assert result == 42

    def test_call_safe_error_returns_tuple(self):
        """Test that call_safe returns (False, error_msg) on error."""
        registry = McpRegistry({})

        def failing_func():
            raise ValueError("Operation failed")

        registry.register_service("test", {"fail": failing_func})
        client = McpClient(registry)

        success, error_msg = client.call_safe("test", "fail")

        assert success is False
        assert "Operation failed" in error_msg

    def test_call_safe_service_not_found(self):
        """Test call_safe error handling for nonexistent service."""
        registry = McpRegistry({})
        client = McpClient(registry)

        success, error_msg = client.call_safe("nonexistent", "func")

        assert success is False
        assert "Service 'nonexistent' not found" in error_msg

    def test_call_safe_function_not_found(self):
        """Test call_safe error handling for nonexistent function."""
        registry = McpRegistry({})
        registry.register_service("test", {"valid": lambda: "ok"})
        client = McpClient(registry)

        success, error_msg = client.call_safe("test", "invalid")

        assert success is False
        assert "Function 'invalid' not found" in error_msg

    def test_call_safe_strips_error_prefix(self):
        """Test that call_safe strips 'MCP call failed:' prefix from errors."""
        registry = McpRegistry({})

        def error_func():
            raise RuntimeError("Custom error message")

        registry.register_service("test", {"error": error_func})
        client = McpClient(registry)

        success, error_msg = client.call_safe("test", "error")

        assert success is False
        assert "Custom error message" in error_msg
        # Verify prefix was stripped
        assert not error_msg.startswith("MCP call failed:")

    def test_call_safe_handles_unexpected_exceptions(self):
        """Test that call_safe catches unexpected exceptions."""
        registry = Mock(spec=McpRegistry)

        # Mock dispatch to raise unexpected exception
        registry.dispatch.side_effect = RuntimeError("Unexpected error")

        client = McpClient(registry)
        success, error_msg = client.call_safe("service", "func")

        assert success is False
        assert "Unexpected error" in error_msg

    def test_call_safe_with_none_return_value(self):
        """Test that call_safe correctly handles None return values."""
        registry = McpRegistry({})

        def returns_none():
            return None

        registry.register_service("test", {"none_func": returns_none})
        client = McpClient(registry)

        success, result = client.call_safe("test", "none_func")

        assert success is True
        assert result is None

    def test_call_safe_no_exception_for_errors(self):
        """Test that call_safe never raises exceptions."""
        registry = McpRegistry({})

        def always_fails():
            raise Exception("Critical error")

        registry.register_service("test", {"fail": always_fails})
        client = McpClient(registry)

        # Should not raise exception
        success, error_msg = client.call_safe("test", "fail")

        assert success is False
        assert isinstance(error_msg, str)


class TestMcpClientListServices:
    """Test suite for McpClient.list_services() method."""

    def test_list_services_returns_all_registered(self):
        """Test that list_services returns all services from registry."""
        registry = McpRegistry({})

        registry.register_service("service1", {
            "func1": lambda: 1,
            "func2": lambda: 2
        })
        registry.register_service("service2", {
            "func3": lambda: 3
        })

        client = McpClient(registry)
        services = client.list_services()

        assert len(services) == 2
        assert services["service1"] == ["func1", "func2"]
        assert services["service2"] == ["func3"]

    def test_list_services_empty_registry(self):
        """Test list_services returns empty dict for new registry."""
        registry = McpRegistry({})
        client = McpClient(registry)

        services = client.list_services()

        assert services == {}


class TestMcpClientIntegration:
    """Integration tests for realistic McpClient usage patterns."""

    def test_client_workflow_with_multiple_calls(self):
        """Test realistic workflow with multiple service calls."""
        registry = McpRegistry({})

        # Register file service
        file_data = {"users.txt": "Alice\nBob\nCharlie"}

        def file_exists(path):
            return path in file_data

        def read_file(path):
            if path not in file_data:
                raise FileNotFoundError(f"File not found: {path}")
            return file_data[path]

        registry.register_service("file_specialist", {
            "file_exists": file_exists,
            "read_file": read_file
        })

        # Register string service
        def count_lines(text):
            return len(text.split("\n"))

        registry.register_service("string_specialist", {
            "count_lines": count_lines
        })

        client = McpClient(registry)

        # Workflow: Check if file exists, read it, count lines
        path = "users.txt"

        # Step 1: Check existence
        exists = client.call("file_specialist", "file_exists", path=path)
        assert exists is True

        # Step 2: Read file
        contents = client.call("file_specialist", "read_file", path=path)
        assert "Alice" in contents

        # Step 3: Count lines
        line_count = client.call("string_specialist", "count_lines", text=contents)
        assert line_count == 3

    def test_client_error_recovery_with_call_safe(self):
        """Test error recovery pattern using call_safe."""
        registry = McpRegistry({})

        cache = {}

        def get_from_cache(key):
            if key not in cache:
                raise KeyError(f"Cache miss: {key}")
            return cache[key]

        def get_from_database(key):
            # Simulate database lookup
            return f"db_value_{key}"

        registry.register_service("cache", {"get": get_from_cache})
        registry.register_service("database", {"get": get_from_database})

        client = McpClient(registry)

        # Try cache first, fallback to database
        key = "user_123"

        success, result = client.call_safe("cache", "get", key=key)

        if not success:
            # Cache miss, try database
            result = client.call("database", "get", key=key)

        assert result == "db_value_user_123"

    def test_client_chained_service_calls(self):
        """Test chaining multiple service calls together."""
        registry = McpRegistry({})

        # Service 1: Data fetcher
        def fetch_data(source):
            return {"source": source, "raw_data": [1, 2, 3, 4, 5]}

        # Service 2: Data transformer
        def transform(data):
            return [x * 2 for x in data["raw_data"]]

        # Service 3: Data aggregator
        def aggregate(values):
            return {"sum": sum(values), "count": len(values), "avg": sum(values) / len(values)}

        registry.register_service("fetcher", {"fetch": fetch_data})
        registry.register_service("transformer", {"transform": transform})
        registry.register_service("aggregator", {"aggregate": aggregate})

        client = McpClient(registry)

        # Chain: fetch → transform → aggregate
        raw = client.call("fetcher", "fetch", source="api")
        transformed = client.call("transformer", "transform", data=raw)
        final = client.call("aggregator", "aggregate", values=transformed)

        assert final["sum"] == 30  # (1+2+3+4+5) * 2
        assert final["count"] == 5
        assert final["avg"] == 6.0

    def test_client_preserves_request_id_for_tracing(self):
        """Test that request_id flows through for distributed tracing."""
        registry = Mock(spec=McpRegistry)

        response = McpResponse(
            status="success",
            data="result",
            request_id="trace-abc-123"
        )
        registry.dispatch.return_value = response

        client = McpClient(registry)
        result = client.call("service", "func", param="value")

        # Verify request had auto-generated ID
        request = registry.dispatch.call_args[0][0]
        assert request.request_id is not None

        # In real usage, response.request_id would match request.request_id
        assert response.request_id == "trace-abc-123"
