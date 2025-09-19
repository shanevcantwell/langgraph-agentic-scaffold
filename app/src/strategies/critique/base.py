# In: app/src/strategies/critique/base.py

from abc import ABC, abstractmethod
from app.src.specialists.schemas import Critique
from app.src.graph.state import GraphState

class BaseCritiqueStrategy(ABC):
    """Defines the contract for any pluggable critique behavior."""

    @abstractmethod
    def critique(self, state: GraphState) -> Critique:
        """
        Analyzes the state and returns a structured Critique.

        Args:
            state: The full GraphState, providing maximum context.

        Returns:
            A structured Critique object with a decision and feedback.
        """
        pass
