import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class ContextEngineeringSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        # CONTEXT ENGINEERING SUBGRAPH
        # Triage (entry point, gate) -> [SA | END]
        # SA (planning) -> Facilitator (context assembly) -> Router
        #
        # Triage runs first as a pass/fail classifier on the user's prompt.
        # Rejection via ask_user happens before SA invests an LLM call on planning.
        # SA plans from a validated prompt, then Facilitator assembles gathered_context.

        if "triage_architect" in self.specialists:
            # Triage conditional: PASS -> SA, CLARIFY -> END (reject with cause)
            workflow.add_conditional_edges(
                "triage_architect",
                self.orchestrator.check_triage_outcome,
                {
                    "systems_architect": "systems_architect",
                    CoreSpecialist.END.value: CoreSpecialist.END.value
                }
            )
            logger.info("Graph Edge: Added TriageArchitect conditional edge (PASS->SA, CLARIFY->END)")

        if "systems_architect" in self.specialists and "facilitator_specialist" in self.specialists:
            # SA produces task_plan, then Facilitator assembles gathered_context
            workflow.add_edge("systems_architect", "facilitator_specialist")
            logger.info("Graph Edge: Added SystemsArchitect -> Facilitator edge")

        if "facilitator_specialist" in self.specialists:
            workflow.add_edge("facilitator_specialist", CoreSpecialist.ROUTER.value)
            logger.info("Graph Edge: Added Facilitator -> Router edge")

    def get_excluded_specialists(self) -> list[str]:
        """Return specialists that have dedicated edges and shouldn't be in the general router menu."""
        excluded = []
        if "systems_architect" in self.specialists:
            excluded.append("systems_architect")
        if "triage_architect" in self.specialists:
            excluded.append("triage_architect")
        if "facilitator_specialist" in self.specialists:
            excluded.append("facilitator_specialist")
        return excluded
