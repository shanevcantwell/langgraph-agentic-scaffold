"""
MCP Registry - Per-graph-instance registry for MCP service dispatch.

Design: Per-graph-instance (not singleton) for test isolation and multi-graph support.
"""

from typing import Dict, Any, Callable
import logging
import signal
from functools import wraps

from .schemas import McpRequest, McpResponse
from ..utils.errors import McpServiceNotFoundError, McpFunctionNotFoundError, McpInvocationError

logger = logging.getLogger(__name__)


class TimeoutError(Exception):
    """Raised when MCP function execution exceeds timeout."""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout."""
    raise TimeoutError("MCP function execution timed out")


class McpRegistry:
    """
    Per-graph-instance registry of MCP-enabled services.

    Each GraphBuilder creates its own McpRegistry to ensure test isolation
    and support for multiple concurrent graphs.

    Design Decisions:
    - Per-graph scope (not singleton) for test isolation
    - Synchronous execution only (async can be added later)
    - Configurable timeout (default 5 seconds)
    - Optional LangSmith tracing (toggle via config)

    Example:
        registry = McpRegistry(config)
        registry.register_service("file_specialist", {
            "file_exists": my_file_exists_fn,
            "list_files": my_list_files_fn
        })

        request = McpRequest(
            service_name="file_specialist",
            function_name="file_exists",
            parameters={"path": "/workspace/data.txt"}
        )
        response = registry.dispatch(request)
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MCP registry with configuration.

        Args:
            config: Full application config (will extract 'mcp' section)
        """
        self._services: Dict[str, Dict[str, Callable]] = {}
        self.config = config.get("mcp", {})
        self.tracing_enabled = self.config.get("tracing_enabled", True)
        self.timeout_seconds = self.config.get("timeout_seconds", 5)

        logger.info(
            f"Initialized McpRegistry (tracing={'enabled' if self.tracing_enabled else 'disabled'}, "
            f"timeout={self.timeout_seconds}s)"
        )

    def register_service(self, service_name: str, functions: Dict[str, Callable]):
        """
        Register a specialist's functions as MCP services.

        Args:
            service_name: Name of the service (typically specialist_name)
            functions: Map of function_name -> callable

        Raises:
            ValueError: If service already registered or functions is empty
        """
        if not functions:
            raise ValueError(f"Cannot register service '{service_name}' with empty function map")

        if service_name in self._services:
            logger.warning(
                f"Service '{service_name}' already registered. Overwriting with {len(functions)} functions."
            )

        self._services[service_name] = functions
        function_names = list(functions.keys())
        logger.info(f"Registered MCP service '{service_name}' with functions: {function_names}")

    def get_service(self, service_name: str) -> Dict[str, Callable]:
        """
        Get registered functions for a service.

        Args:
            service_name: Name of the service

        Returns:
            Dictionary of function_name -> callable

        Raises:
            McpServiceNotFoundError: If service not registered
        """
        if service_name not in self._services:
            available = list(self._services.keys())
            raise McpServiceNotFoundError(
                f"Service '{service_name}' not found in MCP registry. "
                f"Available services: {available}"
            )
        return self._services[service_name]

    def dispatch(self, request: McpRequest) -> McpResponse:
        """
        Synchronously execute MCP function call with timeout.

        Args:
            request: McpRequest with service_name, function_name, parameters

        Returns:
            McpResponse with success/error status and data

        Raises:
            McpServiceNotFoundError: If service doesn't exist
            McpFunctionNotFoundError: If function doesn't exist
            McpInvocationError: If function execution fails
        """
        logger.debug(
            f"MCP dispatch: {request.service_name}.{request.function_name}()"
            f" [request_id={request.request_id}]"
        )

        try:
            # Get service functions
            service = self.get_service(request.service_name)

            # Get specific function
            if request.function_name not in service:
                available_functions = list(service.keys())
                raise McpFunctionNotFoundError(
                    f"Function '{request.function_name}' not found in service '{request.service_name}'. "
                    f"Available functions: {available_functions}"
                )

            function = service[request.function_name]

            # Wrap in trace span if tracing enabled
            if self.tracing_enabled:
                function = self._wrap_with_tracing(function, request)

            # Execute with timeout
            result = self._execute_with_timeout(function, request.parameters)

            # Success response
            response = McpResponse(
                status="success",
                data=result,
                request_id=request.request_id
            )
            logger.debug(f"MCP success: {request.service_name}.{request.function_name}()")
            return response

        except (McpServiceNotFoundError, McpFunctionNotFoundError) as e:
            # These are expected errors (misconfiguration)
            logger.error(f"MCP dispatch error: {e}")
            return McpResponse(
                status="error",
                error_message=str(e),
                request_id=request.request_id
            )

        except TimeoutError as e:
            # Timeout error
            error_msg = f"MCP call timed out after {self.timeout_seconds}s: {request.service_name}.{request.function_name}()"
            logger.error(error_msg)
            return McpResponse(
                status="error",
                error_message=error_msg,
                request_id=request.request_id
            )

        except Exception as e:
            # Unexpected errors during function execution
            error_msg = f"MCP invocation error in {request.service_name}.{request.function_name}(): {str(e)}"
            logger.error(error_msg, exc_info=True)
            return McpResponse(
                status="error",
                error_message=error_msg,
                request_id=request.request_id
            )

    def _execute_with_timeout(self, function: Callable, parameters: Dict[str, Any]) -> Any:
        """
        Execute function with timeout protection.

        Args:
            function: Callable to execute
            parameters: Keyword arguments for function

        Returns:
            Function result

        Raises:
            TimeoutError: If execution exceeds timeout
        """
        # Set up timeout signal handler (Unix only)
        # Note: This won't work on Windows, would need threading.Timer instead
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(self.timeout_seconds)

        try:
            result = function(**parameters)
            signal.alarm(0)  # Cancel alarm
            return result
        finally:
            signal.signal(signal.SIGALRM, old_handler)  # Restore old handler

    def _wrap_with_tracing(self, function: Callable, request: McpRequest) -> Callable:
        """
        Wrap function with LangSmith tracing (if available).

        Args:
            function: Original callable
            request: McpRequest for trace metadata

        Returns:
            Wrapped function (or original if tracing unavailable)
        """
        try:
            from langsmith import traceable

            @traceable(
                name=f"mcp.{request.service_name}.{request.function_name}",
                run_type="tool",
                metadata={
                    "mcp_request_id": request.request_id,
                    "service_name": request.service_name,
                    "function_name": request.function_name,
                }
            )
            @wraps(function)
            def traced_function(**kwargs):
                return function(**kwargs)

            return traced_function

        except ImportError:
            # LangSmith not available, return original function
            logger.debug("LangSmith not available, skipping MCP tracing")
            return function

    def list_services(self) -> Dict[str, list]:
        """
        Get list of all registered services and their functions.

        Returns:
            Dictionary mapping service_name -> list of function names
        """
        return {
            service_name: list(functions.keys())
            for service_name, functions in self._services.items()
        }
