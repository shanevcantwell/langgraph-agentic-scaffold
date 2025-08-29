# app/src/specialists/base.py
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

from ..llm.adapter import BaseAdapter

logger = logging.getLogger(__name__)

class BaseSpecialist(ABC):
    """Abstract base class for all specialists."""

    def __init__(self, specialist_name: str):
        """
        Initializes the specialist. The specialist_config is injected later
        by the ChiefOfStaff.
        """
        self.specialist_name = specialist_name
        self._specialist_config: Dict[str, Any] = {}
        self.llm_adapter: BaseAdapter | None = None
        self.is_enabled = True # Default, updated when config is set.

    @property
    def specialist_config(self) -> Dict[str, Any]:
        """The configuration dictionary for this specific specialist."""
        return self._specialist_config

    @specialist_config.setter
    def specialist_config(self, value: Dict[str, Any]):
        """
        Sets the specialist's configuration and updates related properties
        like 'is_enabled'.
        """
        self._specialist_config = value
        # Update is_enabled whenever the config is set.
        self.is_enabled = self._specialist_config.get("enabled", True)

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
            result = self._execute_logic(state)
        except Exception as e:
            logger.error(f"An unhandled exception occurred in {self.specialist_name}: {e}", exc_info=True)
            return {"error": f"'{self.specialist_name}' encountered a critical error: {e}"}
        logger.info(f"--- Finished specialist: {self.specialist_name} ---")
        return result

    def set_specialist_map(self, specialist_map: Dict[str, Any]):
        """Provides the specialist with a map of other available specialists."""
        # Default implementation does nothing.
        pass