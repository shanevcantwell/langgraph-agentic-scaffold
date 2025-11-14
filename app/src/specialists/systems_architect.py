# app/src/specialists/systems_architect.py

import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import SystemPlan
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    """
    A specialist that analyzes a user request and creates a high-level
    technical plan for implementation, adding it to the state.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name=specialist_name, specialist_config=specialist_config)
        logger.info("---INITIALIZED SystemsArchitect---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        messages: List[BaseMessage] = state.get("messages", [])
        
        # This specialist should operate on the primary messages, not transient text.
        contextual_messages = messages[:] 

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=SystemPlan
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("SystemsArchitect failed to get a valid plan from the LLM.")

        plan = SystemPlan(**json_response)

        new_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have created a system plan: {plan.plan_summary}",
        )
        
        # MODIFICATION: The System Plan is a durable output and MUST be placed
        # in the 'artifacts' dictionary, not the 'scratchpad'.
        updated_state = {
            "messages": [new_message],
            "artifacts": {"system_plan": plan.dict()},
            "scratchpad": {"recommended_specialists": ["web_builder"]}  # Task 2.7: moved to scratchpad
        }
        return updated_state
