from abc import ABC, abstractmethod
from typing import Dict, Any
from langgraph.graph import StateGraph
from ...specialists.base import BaseSpecialist
from ..graph_orchestrator import GraphOrchestrator

class BaseSubgraph(ABC):
    """
    Abstract base class for subgraph builders.
    Subgraphs encapsulate the wiring logic for specific workflow patterns.
    """
    def __init__(self, specialists: Dict[str, BaseSpecialist], orchestrator: GraphOrchestrator, config: Dict[str, Any]):
        self.specialists = specialists
        self.orchestrator = orchestrator
        self.config = config

    @abstractmethod
    def build(self, workflow: StateGraph) -> None:
        """
        Wires the subgraph nodes and edges into the main workflow graph.
        """
        pass

    @abstractmethod
    def get_excluded_specialists(self) -> list[str]:
        """
        Returns a list of specialist names that are part of this subgraph
        and should be excluded from standard hub-and-spoke routing.
        """
        pass
