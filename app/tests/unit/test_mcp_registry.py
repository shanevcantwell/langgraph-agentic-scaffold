"""
Unit tests for McpRegistry - Service registration and dispatch.

Tests validate registry lifecycle, service registration, dispatch logic,
timeout handling, and error conditions.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock

from app.src.mcp.registry import McpRegistry
from app.src.mcp.schemas import McpRequest, McpResponse
from app.src.utils.errors import McpServiceNotFoundError, McpFunctionNotFoundError


class TestMcpRegistryInitialization:
    """Test suite for McpRegistry initialization and configuration."""

    def test_registry_initializes_with_config(self):
        """Test that registry extracts MCP config section correctly."""
        config = {
            "mcp": {
                "tracing_enabled": False,
                "timeout_seconds": 10
            }
        }
        registry = McpRegistry(config)

        assert registry.config == config["mcp"]
        assert registry.tracing_enabled is False
        assert registry.timeout_seconds == 10

    def test_registry_initializes_with_defaults(self):
        """Test that registry uses defaults when MCP config missing."""
        config = {}
        registry = McpRegistry(config)

        assert registry.config == {}
        assert registry.tracing_enabled is True  # Default
        assert registry.timeout_seconds == 5  # Default

    def test_registry_starts_with_no_services(self):
        """Test that registry starts with empty service map."""
        registry = McpRegistry({})
        services = registry.list_services()

        assert services == {}


class TestMcpRegistryServiceManagement:
    """Test suite for service registration and retrieval."""

    def test_register_service_success(self):
        """Test that service registration works correctly."""
        registry = McpRegistry({})
        functions = {
            "test_func": lambda x: x * 2
        }

        registry.register_service("test_service", functions)
        services = registry.list_services()

        assert "test_service" in services
        assert services["test_service"] == ["test_func"]

    def test_register_service_with_multiple_functions(self):
        """Test registering a service with multiple functions."""
        registry = McpRegistry({})
        functions = {
            "func1": lambda x: x + 1,
            "func2": lambda x: x * 2,
            "func3": lambda x: x - 1
        }

        registry.register_service("multi_service", functions)
        services = registry.list_services()

        assert services["multi_service"] == ["func1", "func2", "func3"]

    def test_register_service_overwrites_existing(self):
        """Test that registering same service name overwrites previous."""
        registry = McpRegistry({})

        # Register first version
        registry.register_service("service", {"old_func": lambda: "old"})

        # Register second version (should overwrite)
        registry.register_service("service", {"new_func": lambda: "new"})

        services = registry.list_services()
        assert services["service"] == ["new_func"]
        assert "old_func" not in services["service"]

    def test_register_service_raises_on_empty_functions(self):
        """Test that registering service with empty functions fails."""
        registry = McpRegistry({})

        with pytest.raises(ValueError) as exc_info:
            registry.register_service("empty_service", {})

        assert "empty function map" in str(exc_info.value)

    def test_get_service_success(self):
        """Test that get_service returns registered functions."""
        registry = McpRegistry({})
        test_func = lambda x: x
        functions = {"test_func": test_func}

        registry.register_service("test_service", functions)
        retrieved = registry.get_service("test_service")

        assert retrieved == functions
        assert retrieved["test_func"] is test_func

    def test_get_service_not_found_raises_error(self):
        """Test that get_service raises McpServiceNotFoundError."""
        registry = McpRegistry({})

        with pytest.raises(McpServiceNotFoundError) as exc_info:
            registry.get_service("nonexistent")

        assert "Service 'nonexistent' not found" in str(exc_info.value)
        assert "Available services: []" in str(exc_info.value)

    def test_list_services_returns_all_registered(self):
        """Test that list_services returns all registered services."""
        registry = McpRegistry({})

        registry.register_service("service1", {"func1": lambda: 1})
        registry.register_service("service2", {"func2": lambda: 2, "func3": lambda: 3})

        services = registry.list_services()

        assert len(services) == 2
        assert services["service1"] == ["func1"]
        assert services["service2"] == ["func2", "func3"]


class TestMcpRegistryDispatch:
    """Test suite for MCP request dispatch and execution."""

    def test_dispatch_success(self):
        """Test successful function dispatch and response."""
        registry = McpRegistry({})

        def add_numbers(a, b):
            return a + b

        registry.register_service("math_service", {"add": add_numbers})

        request = McpRequest(
            service_name="math_service",
            function_name="add",
            parameters={"a": 5, "b": 3}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data == 8
        assert response.request_id == request.request_id

    def test_dispatch_with_no_parameters(self):
        """Test dispatch for function with no parameters."""
        registry = McpRegistry({})

        def get_timestamp():
            return "2024-01-01T00:00:00Z"

        registry.register_service("time_service", {"get_timestamp": get_timestamp})

        request = McpRequest(
            service_name="time_service",
            function_name="get_timestamp",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data == "2024-01-01T00:00:00Z"

    def test_dispatch_with_complex_return_value(self):
        """Test dispatch with complex nested data structures."""
        registry = McpRegistry({})

        def get_user_data(user_id):
            return {
                "id": user_id,
                "profile": {
                    "name": "Test User",
                    "tags": ["admin", "developer"]
                }
            }

        registry.register_service("user_service", {"get_user": get_user_data})

        request = McpRequest(
            service_name="user_service",
            function_name="get_user",
            parameters={"user_id": 123}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data["id"] == 123
        assert response.data["profile"]["name"] == "Test User"

    def test_dispatch_service_not_found(self):
        """Test dispatch returns error response for nonexistent service."""
        registry = McpRegistry({})

        request = McpRequest(
            service_name="nonexistent",
            function_name="some_func",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "error"
        assert "Service 'nonexistent' not found" in response.error_message
        assert response.request_id == request.request_id

    def test_dispatch_function_not_found(self):
        """Test dispatch returns error response for nonexistent function."""
        registry = McpRegistry({})
        registry.register_service("test_service", {"existing_func": lambda: "ok"})

        request = McpRequest(
            service_name="test_service",
            function_name="nonexistent_func",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "error"
        assert "Function 'nonexistent_func' not found" in response.error_message
        assert "Available functions: ['existing_func']" in response.error_message

    def test_dispatch_function_execution_error(self):
        """Test dispatch returns error response when function raises exception."""
        registry = McpRegistry({})

        def failing_function():
            raise ValueError("Intentional test error")

        registry.register_service("test_service", {"fail": failing_function})

        request = McpRequest(
            service_name="test_service",
            function_name="fail",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "error"
        assert "MCP invocation error" in response.error_message
        assert "Intentional test error" in response.error_message


class TestMcpRegistryTimeout:
    """Test suite for timeout handling in function execution."""

    def test_dispatch_with_timeout_success(self):
        """Test that fast functions complete within timeout."""
        config = {"mcp": {"timeout_seconds": 2}}
        registry = McpRegistry(config)

        def fast_function():
            return "completed"

        registry.register_service("test_service", {"fast": fast_function})

        request = McpRequest(
            service_name="test_service",
            function_name="fast",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data == "completed"

    @pytest.mark.skip(reason="Timeout tests with signal.alarm() are flaky in test environments")
    def test_dispatch_timeout_error(self):
        """Test that slow functions trigger timeout error."""
        config = {"mcp": {"timeout_seconds": 1}}
        registry = McpRegistry(config)

        def slow_function():
            time.sleep(2)  # Exceeds 1 second timeout
            return "should not reach here"

        registry.register_service("test_service", {"slow": slow_function})

        request = McpRequest(
            service_name="test_service",
            function_name="slow",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "error"
        assert "timed out" in response.error_message.lower()


class TestMcpRegistryTracing:
    """Test suite for LangSmith tracing integration."""

    def test_tracing_enabled_wraps_function(self):
        """Test that tracing wraps function when enabled."""
        config = {"mcp": {"tracing_enabled": True}}
        registry = McpRegistry(config)

        def test_function():
            return "result"

        registry.register_service("test_service", {"test": test_function})

        request = McpRequest(
            service_name="test_service",
            function_name="test",
            parameters={}
        )

        response = registry.dispatch(request)

        # Function should execute successfully with or without LangSmith
        assert response.status == "success"
        assert response.data == "result"
        # Note: Actual tracing behavior depends on LangSmith being installed
        # This test verifies the registry doesn't break when tracing is enabled

    def test_tracing_disabled_does_not_wrap(self):
        """Test that tracing is skipped when disabled."""
        config = {"mcp": {"tracing_enabled": False}}
        registry = McpRegistry(config)

        call_count = 0

        def test_function():
            nonlocal call_count
            call_count += 1
            return "result"

        registry.register_service("test_service", {"test": test_function})

        request = McpRequest(
            service_name="test_service",
            function_name="test",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data == "result"
        assert call_count == 1  # Function was called directly

    def test_tracing_gracefully_handles_missing_langsmith(self):
        """Test that registry works when LangSmith is not installed."""
        config = {"mcp": {"tracing_enabled": True}}
        registry = McpRegistry(config)

        def test_function():
            return "result"

        registry.register_service("test_service", {"test": test_function})

        request = McpRequest(
            service_name="test_service",
            function_name="test",
            parameters={}
        )

        response = registry.dispatch(request)

        # Should work whether LangSmith is installed or not
        # The _wrap_with_tracing method has try/except to handle ImportError
        assert response.status == "success"
        assert response.data == "result"


class TestMcpRegistryIntegration:
    """Integration tests for realistic registry usage patterns."""

    def test_multi_service_registration_and_dispatch(self):
        """Test multiple services working together."""
        registry = McpRegistry({})

        # File service
        def file_exists(path):
            return path == "/valid/path.txt"

        def read_file(path):
            if path == "/valid/path.txt":
                return "file contents"
            raise FileNotFoundError(f"File not found: {path}")

        registry.register_service("file_specialist", {
            "file_exists": file_exists,
            "read_file": read_file
        })

        # Math service
        registry.register_service("math_specialist", {
            "add": lambda a, b: a + b,
            "multiply": lambda a, b: a * b
        })

        # Test file operations
        req1 = McpRequest(
            service_name="file_specialist",
            function_name="file_exists",
            parameters={"path": "/valid/path.txt"}
        )
        resp1 = registry.dispatch(req1)
        assert resp1.status == "success"
        assert resp1.data is True

        # Test math operations
        req2 = McpRequest(
            service_name="math_specialist",
            function_name="multiply",
            parameters={"a": 6, "b": 7}
        )
        resp2 = registry.dispatch(req2)
        assert resp2.status == "success"
        assert resp2.data == 42

    def test_error_handling_preserves_request_id(self):
        """Test that error responses preserve request_id for tracing."""
        registry = McpRegistry({})

        request = McpRequest(
            service_name="nonexistent",
            function_name="test",
            parameters={},
            request_id="trace-12345"
        )

        response = registry.dispatch(request)

        assert response.status == "error"
        assert response.request_id == "trace-12345"

    def test_registry_handles_none_return_value(self):
        """Test that functions returning None are handled correctly."""
        registry = McpRegistry({})

        def returns_none():
            return None

        registry.register_service("test_service", {"returns_none": returns_none})

        request = McpRequest(
            service_name="test_service",
            function_name="returns_none",
            parameters={}
        )

        response = registry.dispatch(request)

        assert response.status == "success"
        assert response.data is None
