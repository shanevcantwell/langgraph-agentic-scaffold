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
        specialist_config = ConfigLoader().get_specialist_config(specialist_name)
        prompt_file = specialist_config.get("prompt_file")
        system_prompt = load_prompt(prompt_file) if prompt_file else ""
        self.llm_adapter = AdapterFactory().create_adapter(
            specialist_name=specialist_name,
            system_prompt=system_prompt
        )
        logger.info(f"---INITIALIZED BASE ({self.__class__.__name__})---")

    @abstractmethod
    def execute(self, state: dict) -> Dict[str, Any]:
        """
        The execution method called by the LangGraph node.
        """
        pass
