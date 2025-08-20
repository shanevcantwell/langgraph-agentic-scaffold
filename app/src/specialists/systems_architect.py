import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas import SystemPlan
from langchain_core.messages import AIMessage, BaseMessage

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    """
    A specialist that analyzes a user request and creates a high-level
    technical plan for implementation, adding it to the state.
    """
    def __init__(self):
        super().__init__(specialist_name="systems_architect")
        logger.info("---INITIALIZED SystemsArchitect---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]

        request = StandardizedLLMRequest(
            messages=messages,
            output_model_class=SystemPlan
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("SystemsArchitect failed to get a valid plan from the LLM.")

        plan = SystemPlan(**json_response)

        # Add a summary message for the router and a structured artifact for other specialists/API response
        new_message = AIMessage(content=f"I have created a system plan: {plan.plan_summary}")
        updated_state = {
            "messages": state["messages"] + [new_message],
            "system_plan": plan.dict(),
            "next_specialist": "web_builder" # Set next specialist
        }
        return updated_state
