import logging
from langgraph.graph import StateGraph
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)


class EmergentProjectSubgraph(BaseSubgraph):
    """
    Emergent Project Subgraph — placeholder for future extensions.

    ProjectDirector handles iteration internally via react_step MCP.
    Standard hub-and-spoke edges are wired by GraphBuilder.
    No custom graph wiring is needed.
    """

    def build(self, workflow: StateGraph) -> None:
        """No special wiring needed — PD uses react_step internally."""
        if "project_director" not in self.specialists:
            logger.debug("EmergentProjectSubgraph: 'project_director' not found. Skipping.")
            return

        logger.info(
            "EmergentProjectSubgraph: ProjectDirector uses react_step for internal iteration. "
            "No custom graph edges required."
        )

    def get_excluded_specialists(self) -> list[str]:
        """No specialists excluded from hub-and-spoke."""
        return []

    def get_router_excluded_specialists(self) -> list[str]:
        """All specialists available to Router."""
        return []
