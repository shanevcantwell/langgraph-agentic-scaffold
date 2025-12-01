import logging
from langgraph.graph import StateGraph
from .base_subgraph import BaseSubgraph
from ...enums import CoreSpecialist

logger = logging.getLogger(__name__)

class EmergentProjectSubgraph(BaseSubgraph):
    """
    Wires the Emergent Project Subgraph (RECESS Pattern).
    Flow: ProjectDirector -> WebSpecialist -> ProjectDirector -> ... -> Router
    """

    def build(self, workflow: StateGraph) -> None:
        # Check if required specialists are present
        if "project_director" not in self.specialists:
            logger.debug("EmergentProjectSubgraph: 'project_director' not found. Skipping wiring.")
            return

        # Wire ProjectDirector -> (WebSpecialist OR Router)
        workflow.add_conditional_edges(
            "project_director",
            self.orchestrator.after_project_director,
            {
                "web_specialist": "web_specialist",
                CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value
            }
        )
        logger.info("EmergentProjectSubgraph: Wired ProjectDirector edges.")

        # Wire WebSpecialist -> (ProjectDirector OR Router)
        if "web_specialist" in self.specialists:
            workflow.add_conditional_edges(
                "web_specialist",
                self.orchestrator.after_web_specialist,
                {
                    "project_director": "project_director",
                    CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value
                }
            )
            logger.info("EmergentProjectSubgraph: Wired WebSpecialist edges.")

    def get_excluded_specialists(self) -> list[str]:
        """
        These specialists are managed by this subgraph and should not be
        part of the default hub-and-spoke routing (except as entry points).
        """
        return ["project_director", "web_specialist"]
