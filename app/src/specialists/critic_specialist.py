# app/src/specialists/critic_specialist.py
import logging
from typing import Any, Dict

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..strategies.critique.base import BaseCritiqueStrategy

logger = logging.getLogger(__name__)

class CriticSpecialist(BaseSpecialist):
    """
    A specialist that acts as a gatekeeper for quality control. It uses a
    pluggable "Critique Strategy" to analyze an artifact and then makes a
    routing decision based on the outcome.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any], critique_strategy: BaseCritiqueStrategy):
        super().__init__(specialist_name, specialist_config)
        self.strategy = critique_strategy
        self.revision_target = self.specialist_config.get("revision_target")
        logger.info(f"---INITIALIZED CriticSpecialist with strategy: {critique_strategy.__class__.__name__}---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        logger.info(f"Executing CriticSpecialist logic using {self.strategy.__class__.__name__}.")

        # 1. Delegate the core task to the injected strategy
        critique = self.strategy.critique(state)

        # 2. Format the critique into a text artifact for the next specialist
        critique_text_parts = [f"**Overall Assessment:**\n{critique.overall_assessment}\n"]
        if critique.points_for_improvement:
            improvement_points = "\n".join([f"- {point}" for point in critique.points_for_improvement])
            critique_text_parts.append(f"**Points for Improvement:**\n{improvement_points}\n")
        if critique.positive_feedback:
            positive_points = "\n".join([f"- {point}" for point in critique.positive_feedback])
            critique_text_parts.append(f"**What Went Well:**\n{positive_points}")
        critique_text = "\n".join(critique_text_parts)

        # 3. Prepare the state update based on the strategy's decision
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"Critique complete. Decision: {critique.decision}",
        )

        updated_state = {
            "messages": [ai_message],
            "artifacts": {"critique.md": critique_text},
            "scratchpad": {"critique_decision": critique.decision}
        }

        # 4. If the decision is to revise, recommend the configured target
        if critique.decision == "REVISE" and self.revision_target:
            logger.info(f"Critique decision is REVISE. Recommending return to '{self.revision_target}'.")
            updated_state["recommended_specialists"] = [self.revision_target]
        else:
            logger.info(f"Critique decision is ACCEPT. Signaling task completion.")
            updated_state["task_is_complete"] = True

        return updated_state