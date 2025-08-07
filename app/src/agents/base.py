# src/agents/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any

from ..graph.state import GraphState

class SpecialistNode(ABC):
    """
    An abstract base class for a specialist agent node in the LangGraph.

    This class provides a standardized structure for all specialist agents,
    ensuring they are initialized with a system prompt and have a consistent
    execution method for graph integration.
    """

    def __init__(self, system_prompt_path: str):
        """
        Initializes the SpecialistNode by loading its system prompt.

        Args:
            system_prompt_path: The file path to the system prompt text file.
                                This decouples the agent's identity from the code.
        """
        prompt_path = Path(system_prompt_path)
        if not prompt_path.is_file():
            raise FileNotFoundError(f"System prompt file not found at: {system_prompt_path}")
        
        self.system_prompt = prompt_path.read_text()

    @abstractmethod
    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        The main execution method for the node. This will be called by LangGraph.
        """
        pass
