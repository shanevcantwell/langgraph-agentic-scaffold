# app/src/specialists/prompt_triage_specialist.py
import logging
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, BaseMessage
from .base import BaseSpecialist
from ..enums import CoreSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import TriageRecommendations

logger = logging.getLogger(__name__)

class PromptTriageSpecialist(BaseSpecialist):
    """
    A specialist that performs a pre-flight check on the user's initial prompt
    and recommends the next specialist(s) to engage. It uses a constrained
    tool call to ensure its recommendations are valid.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.specialist_map: Dict[str, Dict] = {}
        logger.info("Initialized PromptTriageSpecialist (awaiting contextual configuration).")

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the map of available specialist configurations from the orchestrator."""
        self.specialist_map = specialist_configs
        logger.info("Triage specialist now aware of all available functional specialists.")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # --- Pre-execution check to head off the error ---
        if self.llm_adapter is None:
            logger.error(f"FATAL: Attempted to execute '{self.specialist_name}' but 'self.llm_adapter' is None. This indicates a failure during the graph build process.")
            # Raising a specific error here to make the failure explicit.
            raise RuntimeError(f"'{self.specialist_name}' cannot execute because its LLM adapter was not initialized.")
        messages: List[BaseMessage] = state["messages"]

        if not self.specialist_map:
            logger.error("Triage specialist has no specialist map configured. Cannot make recommendations.")
            return {"scratchpad": {"recommended_specialists": []}}  # Task 2.7: moved to scratchpad

        # Use a tool call to enforce structured output based on the dynamic prompt
        # configured by the GraphBuilder.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[TriageRecommendations]
        )
        
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.warning("Triage LLM did not return a valid tool call. No recommendations will be made.")
            # If Triage fails to make a specific recommendation, explicitly fall back to the
            # general-purpose default_responder_specialist. This prevents the router from having to
            # make a redundant LLM call to arrive at the same conclusion.
            recommendations = [CoreSpecialist.DEFAULT_RESPONDER.value]
        else:
            # The tool call ensures the output is a list of strings. We still validate
            # that the LLM didn't hallucinate a name despite the prompt.
            raw_recommendations = tool_calls[0]['args'].get('recommended_specialists', [])
            if not raw_recommendations:
                logger.warning("Triage LLM returned an empty list of recommendations. Defaulting to default_responder_specialist.")
                raw_recommendations = [CoreSpecialist.DEFAULT_RESPONDER.value]
            recommendations = [rec for rec in raw_recommendations if rec in self.specialist_map]

        logger.info(f"Triage complete. Recommending specialists: {recommendations}")

        # Triage is a silent orchestration step. It should not add a conversational
        # message to the history, as this can confuse downstream specialists.
        # It only updates the state with its recommendations.
        return {
            "scratchpad": {
                "recommended_specialists": recommendations,  # Task 2.7: moved to scratchpad
                "triage_recommendations": recommendations   # Persist for final report
            }
        }