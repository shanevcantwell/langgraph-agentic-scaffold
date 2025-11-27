import logging
from langgraph.graph import StateGraph
from ...enums import CoreSpecialist
from .base_subgraph import BaseSubgraph

logger = logging.getLogger(__name__)

class TieredChatSubgraph(BaseSubgraph):
    def build(self, workflow: StateGraph) -> None:
        # CORE-CHAT-002: Wire tiered chat subgraph (fan-out/join pattern)
        # If all components are present, wire the parallel execution pattern
        has_tiered_chat = ("progenitor_alpha_specialist" in self.specialists and
                          "progenitor_bravo_specialist" in self.specialists and
                          "tiered_synthesizer_specialist" in self.specialists)

        if has_tiered_chat:
            # CRITICAL: Use array syntax so synthesizer waits for BOTH progenitors
            # This is the "join" in the fan-out/join pattern
            workflow.add_edge(
                ["progenitor_alpha_specialist", "progenitor_bravo_specialist"],
                "tiered_synthesizer_specialist"
            )
            logger.info("Graph Edge: Added fan-in edge for tiered chat subgraph (CORE-CHAT-002)")

            # Wire synthesizer to check_task_completion (it sets task_is_complete: True)
            workflow.add_conditional_edges(
                "tiered_synthesizer_specialist",
                self.orchestrator.check_task_completion,
                {CoreSpecialist.END.value: CoreSpecialist.END.value, CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value}
            )

    def get_excluded_specialists(self) -> list[str]:
        has_tiered_chat = ("progenitor_alpha_specialist" in self.specialists and
                          "progenitor_bravo_specialist" in self.specialists and
                          "tiered_synthesizer_specialist" in self.specialists)
        
        if has_tiered_chat:
            return [
                "progenitor_alpha_specialist",
                "progenitor_bravo_specialist",
                "tiered_synthesizer_specialist"
            ]
        return []
