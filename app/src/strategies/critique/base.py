# In: app/src/strategies/critique/base.py

from abc import ABC, abstractmethod
from app.src.graph.state import GraphState
from app.src.specialists.schemas import Critique

class BaseCritiqueStrategy(ABC):
    """
    Defines the abstract contract for any pluggable critique behavior.
    A strategy is a self-contained unit of logic for performing a critique.
    """

    @abstractmethod
    def critique(self, state: GraphState) -> Critique:
        """
        Analyzes the relevant artifacts in the state and returns a structured Critique.
        Args:
            state: The full GraphState, providing maximum context for the strategy.
        Returns:
            A structured Critique object containing the decision and feedback.
        """
        pass
