import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class ContextEngineeringSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        # CONTEXT ENGINEERING SUBGRAPH
        # TriageArchitect -> [Facilitator | Router]
        # Facilitator -> Router
        if "triage_architect" in self.specialists:
            # ADR-CORE-018: Simplified routing - all plans with actions go through Facilitator chain
            # Facilitator → Dialogue → Router handles both context-gathering and ask_user actions
            workflow.add_conditional_edges(
                "triage_architect",
                self.orchestrator.check_triage_outcome,
                {
                    "facilitator_specialist": "facilitator_specialist",
                    CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value,
                    CoreSpecialist.END.value: CoreSpecialist.END.value
                }
            )
            logger.info("Graph Edge: Added TriageArchitect conditional edge (ADR-CORE-018)")

        if "facilitator_specialist" in self.specialists:
            # ADR-CORE-018: Facilitator → Dialogue → Router
            # DialogueSpecialist checks for ASK_USER actions after automated context gathering
            if "dialogue_specialist" in self.specialists:
                workflow.add_edge("facilitator_specialist", "dialogue_specialist")
                workflow.add_edge("dialogue_specialist", CoreSpecialist.ROUTER.value)
                logger.info("Graph Edge: Added Facilitator -> Dialogue -> Router chain (ADR-CORE-018)")
            else:
                # Fallback if DialogueSpecialist not loaded
                workflow.add_edge("facilitator_specialist", CoreSpecialist.ROUTER.value)
                logger.info("Graph Edge: Added Facilitator -> Router edge (DialogueSpecialist not loaded)")

    def get_excluded_specialists(self) -> list[str]:
        excluded = []
        if "triage_architect" in self.specialists:
            excluded.append("triage_architect")
        if "facilitator_specialist" in self.specialists:
            excluded.append("facilitator_specialist")
        if "dialogue_specialist" in self.specialists:
            excluded.append("dialogue_specialist")
        return excluded
