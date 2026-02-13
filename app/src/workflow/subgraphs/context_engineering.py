import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class ContextEngineeringSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        # CONTEXT ENGINEERING SUBGRAPH (Issue #171: SA added as entry point)
        # SystemsArchitect -> TriageArchitect -> [Facilitator | Router]
        # Facilitator -> Router

        # Issue #171: SA is the entry point — produces task_plan, then hands off to Triage
        if "systems_architect" in self.specialists and "triage_architect" in self.specialists:
            workflow.add_edge("systems_architect", "triage_architect")
            logger.info("Graph Edge: Added SystemsArchitect -> TriageArchitect edge (#171)")

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
            # ADR-CORE-059: DialogueSpecialist deprecated - Facilitator handles ASK_USER inline via interrupt()
            # All context actions (READ_FILE, LIST_DIRECTORY, RESEARCH, ASK_USER) are handled uniformly
            workflow.add_edge("facilitator_specialist", CoreSpecialist.ROUTER.value)
            logger.info("Graph Edge: Added Facilitator -> Router edge (ADR-CORE-059)")

    def get_excluded_specialists(self) -> list[str]:
        """Return specialists that have dedicated edges and shouldn't be in the general router menu."""
        excluded = []
        if "systems_architect" in self.specialists:
            excluded.append("systems_architect")
        if "triage_architect" in self.specialists:
            excluded.append("triage_architect")
        if "facilitator_specialist" in self.specialists:
            excluded.append("facilitator_specialist")
        # Note: dialogue_specialist removed from chain per ADR-CORE-059
        # It's excluded via config.yaml excluded_from instead
        return excluded
