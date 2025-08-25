# app/src/specialists/prompt_triage_specialist.py
import logging
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, BaseMessage
from .base import BaseSpecialist
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
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        self.specialist_map: Dict[str, Dict] = {}
        logger.info("Initialized PromptTriageSpecialist (awaiting contextual configuration).")

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the map of available specialist configurations from the orchestrator."""
        self.specialist_map = specialist_configs
        logger.info("Triage specialist now aware of all available functional specialists.")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]

        if not self.specialist_map:
            logger.error("Triage specialist has no specialist map configured. Cannot make recommendations.")
            return {"recommended_specialists": []}

        # Use a tool call to enforce structured output based on the dynamic prompt
        # configured by the ChiefOfStaff.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[TriageRecommendations]
        )
        
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.warning("Triage LLM did not return a valid tool call. No recommendations will be made.")
            recommendations = []
        else:
            # The tool call ensures the output is a list of strings. We still validate
            # that the LLM didn't hallucinate a name despite the prompt.
            raw_recommendations = tool_calls[0]['args'].get('recommended_specialists', [])
            recommendations = [rec for rec in raw_recommendations if rec in self.specialist_map]

        logger.info(f"Triage complete. Recommending specialists: {recommendations}")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content="Initial prompt analysis complete. Passing recommendations to the router.",
        )
        return {
            "messages": [ai_message],
            "recommended_specialists": recommendations
        }