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
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)
        logger.info("---INITIALIZED SystemsArchitect---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        messages: List[BaseMessage] = state.get("messages", [])
        text_to_process = state.get("text_to_process")

        contextual_messages = messages[:] # Make a copy

        # If there's text in the state from another specialist (e.g., file_specialist),
        # add it to the context for the architect to create a more informed plan.
        if text_to_process:
            contextual_messages.append(HumanMessage(
                content=f"Please use the following text as critical context for creating your plan:\n\n---\n{text_to_process}\n---"
            ))

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=SystemPlan
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("SystemsArchitect failed to get a valid plan from the LLM.")

        plan = SystemPlan(**json_response)

        # --- Robustness Check for Refinement Cycles ---
        # Some models fail to set refinement_cycles despite the prompt.
        # We can add a check to enforce it based on the user's original request.
        user_prompt = state["messages"][0].content.lower()
        if plan.refinement_cycles <= 1:
            if "iterate" in user_prompt or "refine" in user_prompt or "twice" in user_prompt or "three times" in user_prompt:
                logger.warning("SystemsArchitect LLM did not set refinement_cycles. Overriding to 2 based on user prompt analysis.")
                plan.refinement_cycles = 2

        # Add a summary message for the router and a structured artifact for other specialists/API response
        new_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have created a system plan: {plan.plan_summary}",
        )
        # Return only the delta (the new changes) to the state, per the "Atomic State Updates" pattern.
        updated_state = {
            "messages": [new_message],
            "system_plan": plan.dict(),
            "recommended_specialists": ["web_builder"]
        }
        return updated_state
