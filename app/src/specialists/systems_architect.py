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
        # "Not me" pattern: if system_plan already exists, don't create another
        # Add self to forbidden_specialists so Router won't route back here
        existing_plan = state.get("artifacts", {}).get("system_plan")
        if existing_plan:
            logger.info("SystemsArchitect: system_plan already exists, adding self to forbidden_specialists")
            return {
                "messages": [create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"A system plan already exists: {existing_plan.get('plan_summary', 'see artifacts')}",
                )],
                "scratchpad": {"forbidden_specialists": [self.specialist_name]},
            }

        # Get enriched messages (includes gathered_context if available)
        messages: List[BaseMessage] = self._get_enriched_messages(state)

        request = StandardizedLLMRequest(
            messages=messages,
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
        
        # System Plan is a durable output - placed in artifacts
        # Add self to forbidden_specialists: job done, don't route back here
        return {
            "messages": [new_message],
            "artifacts": {"system_plan": plan.dict()},
            "scratchpad": {"forbidden_specialists": [self.specialist_name]},
        }
