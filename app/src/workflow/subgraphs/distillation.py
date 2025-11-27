import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class DistillationSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        # DISTILLATION SUBGRAPH: Wire graph-driven iteration pattern
        # If all components are present, wire the coordinator-driven workflow
        has_distillation = ("distillation_coordinator_specialist" in self.specialists and
                           "distillation_prompt_expander_specialist" in self.specialists and
                           "distillation_prompt_aggregator_specialist" in self.specialists and
                           "distillation_response_collector_specialist" in self.specialists)

        if has_distillation:
            # Expansion loop: expander → aggregator → coordinator (checks if more to expand)
            workflow.add_edge("distillation_prompt_expander_specialist", "distillation_prompt_aggregator_specialist")
            workflow.add_conditional_edges(
                "distillation_prompt_aggregator_specialist",
                self.orchestrator.should_continue_expanding,
                {
                    "distillation_prompt_expander_specialist": "distillation_prompt_expander_specialist",  # More seeds
                    "distillation_coordinator_specialist": "distillation_coordinator_specialist"  # Done expanding
                }
            )

            # Collection loop: collector → coordinator (checks if more to collect)
            workflow.add_conditional_edges(
                "distillation_response_collector_specialist",
                self.orchestrator.should_continue_collecting,
                {
                    "distillation_response_collector_specialist": "distillation_response_collector_specialist",  # More prompts
                    "distillation_coordinator_specialist": "distillation_coordinator_specialist"  # Done collecting
                }
            )

            # Coordinator routes based on phase and completion status
            workflow.add_conditional_edges(
                "distillation_coordinator_specialist",
                self.orchestrator.check_task_completion,
                {CoreSpecialist.END.value: CoreSpecialist.END.value, CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value}
            )

            logger.info("Graph Edge: Added distillation subgraph with graph-driven iteration")

    def get_excluded_specialists(self) -> list[str]:
        has_distillation = ("distillation_coordinator_specialist" in self.specialists and
                           "distillation_prompt_expander_specialist" in self.specialists and
                           "distillation_prompt_aggregator_specialist" in self.specialists and
                           "distillation_response_collector_specialist" in self.specialists)
        
        if has_distillation:
            return [
                "distillation_coordinator_specialist",
                "distillation_prompt_expander_specialist",
                "distillation_prompt_aggregator_specialist",
                "distillation_response_collector_specialist"
            ]
        return []
