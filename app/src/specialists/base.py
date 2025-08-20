import logging
from abc import ABC, abstractmethod
from typing import Dict, Any

from ..llm.factory import AdapterFactory
from ..utils.config_loader import ConfigLoader
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class BaseSpecialist(ABC):
    """
    Abstract base class for all specialists in the multi-agent system.
    """

    def __init__(self, specialist_name: str):
        self.specialist_name = specialist_name
        self.specialist_config = ConfigLoader().get_specialist_config(specialist_name)
        prompt_file = self.specialist_config.get("prompt_file")
        system_prompt = load_prompt(prompt_file) if prompt_file else ""
        self.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=specialist_name,
            system_prompt=system_prompt
        )
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        """
        Template method that wraps the specialist's logic with common
        functionality like logging and error handling.
        """
        logger.info(f"---EXECUTING {self.specialist_name.upper()}---")
        logger.debug(f"[{self.specialist_name}] Received state: {state}")
        try:
            updated_state = self._execute_logic(state)
            logger.debug(f"[{self.specialist_name}] Delivering updated state: {updated_state}")
            return updated_state
        except Exception as e:
            logger.error(f"An unhandled exception occurred in {self.specialist_name}: {e}", exc_info=True)
            return {"error": f"{self.specialist_name} encountered a critical error: {e}"}

    @abstractmethod
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        The core logic of the specialist to be implemented by subclasses.
        """
        pass
