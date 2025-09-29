# app/src/specialists/base.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

from ..llm.adapter import BaseAdapter
from ..utils.errors import SpecialistError

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