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
            # Issue #128: Include exit_interview as destination for ACCEPT path
            # after_critique_decider calls check_task_completion on ACCEPT,
            # which routes to exit_interview for validation
            destinations = {
                revision_target: revision_target,
                CoreSpecialist.END.value: CoreSpecialist.END.value,
                CoreSpecialist.ROUTER.value: CoreSpecialist.ROUTER.value,
                CoreSpecialist.CRITIC.value: CoreSpecialist.CRITIC.value  # Self to prevent default looping
            }
            if CoreSpecialist.EXIT_INTERVIEW.value in self.specialists:
                destinations[CoreSpecialist.EXIT_INTERVIEW.value] = CoreSpecialist.EXIT_INTERVIEW.value
            workflow.add_conditional_edges(
                CoreSpecialist.CRITIC.value,
                self.orchestrator.after_critique_decider,
                destinations
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
        # ADR-CORE-012: Both critic and web_builder are subgraph-managed.
        # web_builder's outgoing edges are wired here (after_web_builder),
        # so it MUST be excluded from hub-and-spoke to prevent LangGraph
        # from adding a second parallel branch (classify_interrupt) that
        # leaks into the termination sequence.
        #
        # Note: This only affects OUTGOING edges from web_builder.
        # The router can still route TO web_builder via its destinations map.
        #
        # History: Issue #7 (2025-12-25) removed the exclusion thinking it
        # blocked triage routing, but that was a misunderstanding — exclusion
        # only affects hub-and-spoke outgoing edges, not router destinations.
        # Restored after discovering the parallel branch leak (Feb 2026).
        excluded = []
        if CoreSpecialist.CRITIC.value in self.specialists:
            excluded.append(CoreSpecialist.CRITIC.value)
        if "web_builder" in self.specialists:
            excluded.append("web_builder")
        return excluded
