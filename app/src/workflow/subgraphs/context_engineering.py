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
            # #262: Triage three-way routing based on actions content:
            #   - ask_user only → END (reject with cause)
            #   - context-gathering actions → SA for planning
            #   - empty actions → Facilitator directly (skip SA)
            workflow.add_conditional_edges(
                "triage_architect",
                self.orchestrator.check_triage_outcome,
                {
                    "systems_architect": "systems_architect",
                    "facilitator_specialist": "facilitator_specialist",
                    CoreSpecialist.END.value: CoreSpecialist.END.value,
                }
            )
            logger.info("Graph Edge: Added TriageArchitect conditional edge (actions->SA, empty->Facilitator, ask_user->END)")

        if "systems_architect" in self.specialists and "facilitator_specialist" in self.specialists:
            # #217: SA produces task_plan → Facilitator. SA fails → END (fail-fast).
            # Checks artifacts.task_plan (positive signal) not scratchpad.error (negative).
            workflow.add_conditional_edges(
                "systems_architect",
                self.orchestrator.check_sa_outcome,
                {
                    "facilitator_specialist": "facilitator_specialist",
                    CoreSpecialist.END.value: CoreSpecialist.END.value,
                }
            )
            logger.info("Graph Edge: Added SystemsArchitect conditional edge (task_plan->Facilitator, fail->END)")

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
