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