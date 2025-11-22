# app/src/specialists/base.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

from ..llm.adapter import BaseAdapter
from ..utils.errors import SpecialistError

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

    def execute(self, state: dict) -> Dict[str, Any]:
        """Public method to execute the specialist's task."""
        logger.info(f"--- Executing specialist: {self.specialist_name} ---")
        try:
            result = self._execute_logic(state) or {}
        except Exception as e:
            logger.error(f"Specialist '{self.specialist_name}' raised an exception: {e}", exc_info=True)
            raise SpecialistError(f"Execution failed in '{self.specialist_name}': {e}") from e
        logger.info(f"--- Finished specialist: {self.specialist_name} ---")
        return result

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