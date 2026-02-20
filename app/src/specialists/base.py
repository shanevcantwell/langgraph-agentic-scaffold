# app/src/specialists/base.py
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

from langgraph.errors import GraphInterrupt
from pydantic import ValidationError

from ..llm.adapter import BaseAdapter
from ..utils.errors import SpecialistError
from .schemas import SpecialistResult

if TYPE_CHECKING:
    from ..mcp import McpClient, McpRegistry

logger = logging.getLogger(__name__)

class BaseSpecialist(ABC):
    """Abstract base class for all specialists."""

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initializes the specialist, injecting its configuration via the constructor.
        """
        self.specialist_name = specialist_name
        self.specialist_config = specialist_config
        self.llm_adapter: Optional[BaseAdapter] = None
        self.mcp_client: Optional['McpClient'] = None  # TASK 2.5: Injected by GraphBuilder
        self._compiled_graph = None  # ADR-CORE-045: Injected by WorkflowRunner for fork()
        self.is_enabled = self.specialist_config.get("is_enabled", True)

    @abstractmethod
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """The core logic for the specialist."""
        pass

    def _perform_pre_flight_checks(self) -> bool:
        """
        Performs startup-time checks for external dependencies.
        Returns True if all dependencies are met, False otherwise.
        This default implementation assumes no external dependencies.
        """
        return True

    def _get_enriched_messages(self, state: Dict[str, Any]):
        """
        Get messages with gathered_context injected if available.

        For specialists that interpret user intent (parse requests, create plans,
        route decisions), this ensures they have access to context gathered by
        TriageArchitect/Facilitator before executing their logic.

        Pattern: Append gathered_context as a HumanMessage to the conversation.
        This provides the LLM with directory listings, file contents, search results,
        or other contextual information that helps resolve ambiguous requests.

        Usage:
            # Instead of:
            messages = state.get("messages", [])

            # Use:
            messages = self._get_enriched_messages(state)

        Args:
            state: The graph state containing messages and artifacts

        Returns:
            List of messages with gathered_context appended if present in artifacts
        """
        messages = state.get("messages", [])
        artifacts = state.get("artifacts", {})
        gathered_context = artifacts.get("gathered_context")

        if gathered_context:
            from langchain_core.messages import HumanMessage
            messages = messages + [
                HumanMessage(content=f"[Context gathered by the system]:\n\n{gathered_context}")
            ]
            logger.info(f"{self.__class__.__name__}: Injected gathered_context into LLM input")

        return messages

    def _append_to_gathered_context(self, state: Dict[str, Any], summary: str) -> str:
        """
        Append a summary blurb to gathered_context (read-append-write).

        Specialists use this to leave breadcrumbs for downstream specialists.
        The write-back partner to _get_enriched_messages() which handles the read side.

        Because artifacts use operator.ior (dict merge), writing to the
        "gathered_context" key replaces the previous value. This method
        preserves existing content by reading first and appending.

        Args:
            state: The graph state containing artifacts
            summary: The blurb to append (will be separated by blank lines)

        Returns:
            The updated gathered_context string (caller includes in artifacts dict)
        """
        existing = state.get("artifacts", {}).get("gathered_context", "")
        if existing:
            return f"{existing}\n\n{summary}"
        return summary

    def execute(self, state: dict) -> Dict[str, Any]:
        """Public method to execute the specialist's task."""
        logger.info(f"--- Executing specialist: {self.specialist_name} ---")

        start_time = time.perf_counter()
        error_caught = None
        result = {}

        try:
            result = self._execute_logic(state) or {}
        except GraphInterrupt:
            # ADR-CORE-018: Let interrupt() propagate for HitL workflows
            logger.info(f"Specialist '{self.specialist_name}' triggered interrupt for user clarification")
            raise
        except Exception as e:
            error_caught = e
            logger.error(f"Specialist '{self.specialist_name}' raised an exception: {e}", exc_info=True)
            raise SpecialistError(f"Execution failed in '{self.specialist_name}': {e}") from e
        finally:
            # Training data capture (if enabled)
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            self._capture_training_data(state, result, error_caught, latency_ms)

        # FAIL-FAST: Validate result against SpecialistResult contract
        # This catches task_is_complete in scratchpad immediately rather than silently looping
        try:
            SpecialistResult(**result)  # Validate only - don't transform
        except ValidationError as e:
            raise SpecialistError(
                f"Specialist '{self.specialist_name}' returned invalid result: {e}"
            ) from e

        logger.info(f"--- Finished specialist: {self.specialist_name} ---")
        return result

    def _capture_training_data(
        self,
        input_state: dict,
        output_result: Dict[str, Any],
        error: Optional[Exception],
        latency_ms: int
    ):
        """Capture execution data for training dataset (if enabled)."""
        try:
            from ..observability.training_capture import TrainingCapture

            if not TrainingCapture.is_enabled():
                return

            # Get model ID if available
            model_id = None
            if self.llm_adapter:
                model_id = getattr(self.llm_adapter, "model_id", None)

            # Extract tool calls from result if present
            tool_calls = output_result.get("scratchpad", {}).get("tool_calls", [])

            TrainingCapture.capture_execution(
                specialist_name=self.specialist_name,
                input_state=input_state,
                output_result=output_result,
                tool_calls_made=tool_calls,
                error=error,
                model_id=model_id,
                latency_ms=latency_ms,
                tags=[self.specialist_config.get("type", "unknown")],
            )
        except Exception as capture_error:
            # Never let capture failures affect production execution
            logger.debug(f"Training capture failed (non-critical): {capture_error}")

    def set_specialist_map(self, specialist_map: Dict[str, Any]):
        """Provides the specialist with a map of other available specialists."""
        # Default implementation does nothing.
        pass

    def register_mcp_services(self, registry: 'McpRegistry'):
        """
        Optional: Register this specialist's functions as MCP services.

        Override this method in subclasses to expose functions that other
        specialists can call via McpClient.

        Example:
            def register_mcp_services(self, registry):
                registry.register_service(self.specialist_name, {
                    "file_exists": self._file_exists,
                    "read_file": self._read_file,
                    "list_files": self._list_files
                })

        Args:
            registry: The McpRegistry instance to register services with
        """
        # Default implementation does nothing (specialist doesn't expose MCP services)
        pass