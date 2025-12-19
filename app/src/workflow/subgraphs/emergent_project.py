import logging
from langgraph.graph import StateGraph
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)


class EmergentProjectSubgraph(BaseSubgraph):
    """
    Emergent Project Subgraph (RECESS Pattern) - Phase 2 Implementation.

    In Phase 1, this subgraph wired graph-level cycling between ProjectDirector
    and WebSpecialist. This triggered the 2-step cycle invariant after a few iterations.

    In Phase 2 (ADR-CORE-029), ProjectDirector uses ReActMixin for internal iteration,
    calling WebSpecialist capabilities via MCP instead of graph routing. This means:

    - No special graph wiring needed for ProjectDirector
    - ProjectDirector is a standard hub-and-spoke specialist (returns to Router when done)
    - WebSpecialist remains available for direct routing if needed

    This subgraph now serves as documentation of the pattern and could be extended
    for future HIL (Human-in-the-Loop) checkpointing support per ESM-Foundry roadmap.
    """

    def build(self, workflow: StateGraph) -> None:
        """
        Phase 2: No special wiring needed.

        ProjectDirector handles iteration internally via ReActMixin.
        Standard hub-and-spoke edges are wired by GraphBuilder.
        """
        if "project_director" not in self.specialists:
            logger.debug("EmergentProjectSubgraph: 'project_director' not found. Skipping.")
            return

        # Phase 2: No custom edges - ProjectDirector uses ReActMixin internally
        # and returns to Router via standard hub-and-spoke when research complete.
        logger.info(
            "EmergentProjectSubgraph: ProjectDirector uses ReActMixin for internal iteration. "
            "No custom graph edges required."
        )

    def get_excluded_specialists(self) -> list[str]:
        """
        Phase 2: No specialists excluded from hub-and-spoke.

        Both ProjectDirector and WebSpecialist use standard routing.
        """
        return []

    def get_router_excluded_specialists(self) -> list[str]:
        """
        Phase 2: All specialists available to Router.

        ProjectDirector can be routed to for research tasks.
        WebSpecialist can be routed to for direct web operations.
        """
        return []
