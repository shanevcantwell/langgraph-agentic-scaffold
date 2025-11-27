import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class CriticLoopSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        if CoreSpecialist.CRITIC.value in self.specialists:
            critic_config = self.config.get("specialists", {}).get(CoreSpecialist.CRITIC.value, {})
            revision_target = critic_config.get("revision_target", CoreSpecialist.ROUTER.value)
            workflow.add_conditional_edges(
                CoreSpecialist.CRITIC.value,
                self.orchestrator.after_critique_decider,
                {
                    revision_target: revision_target,
                    CoreSpecialist.END.value: CoreSpecialist.END.value,
                    CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value,
                    CoreSpecialist.CRITIC.value: CoreSpecialist.CRITIC.value # Add self to prevent default looping
                }
            )

            # ADR-CORE-012: WEB_BUILDER ↔ CRITIC SUBGRAPH
            # Creates a tight generate-critique-refine loop without router intervention:
            #   1. Router → web_builder (generates UI)
            #   2. web_builder → critic_specialist (direct edge - reviews UI)
            #   3. critic_specialist → after_critique_decider:
            #      - REVISE → web_builder (refine based on feedback)
            #      - ACCEPT → check_task_completion → END
            # This bypasses the router for efficiency and prevents false loop detection.
            # CRITICAL: web_builder MUST be excluded from hub-and-spoke routing (line 350)
            # Uses conditional edge to check if web_builder succeeded before routing to critic
            if "web_builder" in self.specialists:
                workflow.add_conditional_edges("web_builder", self.orchestrator.after_web_builder)
                logger.info("Graph Edge: Added conditional edge web_builder → [critic_specialist|router] (ADR-CORE-012 subgraph)")

    def get_excluded_specialists(self) -> list[str]:
        excluded = []
        if CoreSpecialist.CRITIC.value in self.specialists:
            excluded.append(CoreSpecialist.CRITIC.value)
        if "web_builder" in self.specialists:
            excluded.append("web_builder")
        return excluded
