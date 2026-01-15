# app/src/dispatchers/base.py
"""
BaseDispatcher - abstract base for operation dispatchers (ADR-CORE-049).

Pattern: Specialist (LLM) → list[Operation] → Dispatcher → Backend

The dispatcher handles "how" (dispatch, error handling, iteration).
Specialists handle "what" (LLM inference produces operation lists).

Design principle: "Security through structure, not through trust."
The ABC enforces that all dispatchers implement:
    - _dispatch_one(): Single operation dispatch to backend
    - _make_error_result(): Error result factory for failed operations

Concrete dispatchers:
    - FileOperationDispatcher: Filesystem MCP operations
    - DroneDispatcher (future): Research drone dispatch with ReAct loops
"""
import asyncio
import concurrent.futures
import logging
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Generic, List, Optional, Protocol, TypeVar, Any

logger = logging.getLogger(__name__)


# Generic type variables for operation and result types
T_Op = TypeVar("T_Op")
T_Result = TypeVar("T_Result")


class HasEventLoop(Protocol):
    """Protocol for backend clients that provide access to event loop."""
    _main_loop: Optional[asyncio.AbstractEventLoop]


class BaseDispatcher(ABC, Generic[T_Op, T_Result]):
    """
    Abstract base for operation dispatchers.

    Pattern: Specialist (LLM) → list[Operation] → Dispatcher → Backend

    Enforces:
    - Async-native dispatch with sync bridge
    - Per-operation error handling (batch doesn't abort on single failure)
    - Consistent logging and timing

    Args:
        backend_client: Client for dispatching operations (must have _main_loop)
        service_name: Service identifier for the backend

    Subclass requirements:
        - Implement _dispatch_one() for single operation dispatch
        - Implement _make_error_result() for error result factory
    """

    def __init__(
        self,
        backend_client: Any,
        service_name: str
    ):
        self.backend_client = backend_client
        self.service_name = service_name

    @abstractmethod
    async def _dispatch_one(self, operation: T_Op) -> T_Result:
        """
        Dispatch single operation to backend.

        Args:
            operation: The operation to dispatch

        Returns:
            Result of the operation

        Note:
            This method should handle its own exceptions and return
            appropriate error results when possible. Only raise for
            unrecoverable errors.
        """
        pass

    @abstractmethod
    def _make_error_result(self, operation: T_Op, error: str) -> T_Result:
        """
        Create error result for failed operation.

        Args:
            operation: The operation that failed
            error: Error message

        Returns:
            Error result appropriate for the operation type
        """
        pass

    async def dispatch(
        self,
        operations: List[T_Op]
    ) -> AsyncGenerator[T_Result, None]:
        """
        Execute operations, yielding results as they complete.

        Default implementation is sequential. Subclasses may override
        for parallel dispatch (e.g., DroneDispatcher).

        Args:
            operations: List of operations to dispatch

        Yields:
            Result for each operation
        """
        class_name = self.__class__.__name__
        logger.info(f"{class_name}: dispatching {len(operations)} operations")

        for i, op in enumerate(operations, 1):
            logger.debug(f"Operation {i}/{len(operations)}: {op}")
            try:
                result = await self._dispatch_one(op)
            except Exception as e:
                logger.warning(f"{class_name}: operation {i} failed: {e}")
                result = self._make_error_result(op, str(e))
            yield result

    def dispatch_sync(
        self,
        operations: List[T_Op],
        timeout: float = 60.0
    ) -> List[T_Result]:
        """
        Sync wrapper for dispatch() - for use in sync specialist code.

        Uses run_coroutine_threadsafe to schedule on main event loop
        (same pattern as sync_call_external_mcp, see GitHub #28).

        Args:
            operations: List of operations to dispatch
            timeout: Seconds to wait for all operations

        Returns:
            List of results for all operations

        Raises:
            RuntimeError: If event loop not available or timeout
        """
        event_loop = self._get_event_loop()
        if event_loop is None:
            raise RuntimeError(
                f"{self.__class__.__name__}: Backend client not initialized. "
                "Ensure connect_all_from_config() was called."
            )

        async def collect_results() -> List[T_Result]:
            results = []
            async for result in self.dispatch(operations):
                results.append(result)
            return results

        class_name = self.__class__.__name__
        logger.debug(f"{class_name}.dispatch_sync: scheduling {len(operations)} ops")

        future = asyncio.run_coroutine_threadsafe(
            collect_results(),
            event_loop
        )

        try:
            results = future.result(timeout=timeout)
            success_count = sum(1 for r in results if getattr(r, 'success', False))
            logger.info(
                f"{class_name}.dispatch_sync: completed {len(results)} ops, "
                f"{success_count} succeeded"
            )
            return results
        except concurrent.futures.TimeoutError:
            raise RuntimeError(
                f"{class_name} timed out after {timeout}s "
                f"with {len(operations)} operations"
            )

    def _get_event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """
        Get event loop from backend client.

        Override if backend client uses different attribute name.
        """
        return getattr(self.backend_client, '_main_loop', None)
