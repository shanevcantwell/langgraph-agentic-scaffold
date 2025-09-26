import logging
from typing import Any, Dict

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..strategies.critique.base import BaseCritiqueStrategy
from ..specialists.schemas import StatusEnum

logger = logging.getLogger(__name__)

class CriticSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any], critique_strategy: BaseCritiqueStrategy):
        super().__init__(specialist_name, specialist_config)
        self.strategy = critique_strategy
        self.revision_target = self.specialist_config.get("revision_target")
        logger.info(f"---INITIALIZED CriticSpecialist with strategy: {critique_strategy.__class__.__name__}---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        logger.info(f"Executing CriticSpecialist logic by delegating to {self.strategy.__class__.__name__}.")

        # 1. Delegate the core task to the injected strategy.
        critique_output = self.strategy.critique(state) # type: ignore

        # 2. Handle Unrecoverable Failure from the Strategy.
        if critique_output.status == StatusEnum.FAILURE:
            error_message = f"The quality gate specialist ({self.specialist_name}) failed because its critique strategy encountered an unrecoverable error: {critique_output.rationale}"
            logger.error(error_message)
            
            return {
                "error": error_message,
                "messages": [create_llm_message(self.specialist_name, self.llm_adapter, f"FATAL ERROR: {error_message}")],
                "artifacts": {"critique.md": f"**Overall Assessment:**\nFATAL ERROR: {error_message}"}
            }

        # 3. Handle Normal Operation.
        critique = critique_output.payload
        critique_text_parts = [f"**Overall Assessment:**\n{critique.overall_assessment}\n"]
        if critique.points_for_improvement:
            improvement_points = "\n".join([f"- {point}" for point in critique.points_for_improvement])
            critique_text_parts.append(f"**Points for Improvement:**\n{improvement_points}\n")
        if critique.positive_feedback:
            positive_points = "\n".join([f"- {point}" for point in critique.positive_feedback])
            critique_text_parts.append(f"**What Went Well:**\n{positive_points}")
        critique_text = "\n".join(critique_text_parts)

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

        if critique.decision == "REVISE" and self.revision_target:
            logger.info(f"Critique decision is REVISE. Recommending return to '{self.revision_target}'.")
            updated_state["recommended_specialists"] = [self.revision_target]
        else: # ACCEPT
            logger.info(f"Critique decision is ACCEPT. Signaling task completion to the Router.")
            updated_state["task_is_complete"] = True

        return updated_state
