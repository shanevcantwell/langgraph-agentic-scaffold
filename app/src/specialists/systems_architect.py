import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_llm_message, create_missing_artifact_response
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
        user_prompt = messages[0].content.lower()

        contextual_messages = messages[:] # Make a copy

        # If the prompt mentions a file like README.md and we don't have its content,
        # we need to inform the LLM about the potential accessibility issue due to sandboxing.
        # This is more robust than making a hard-coded recommendation for a file that
        # may not be in the accessible workspace.
        if "readme.md" in user_prompt and not text_to_process:
            logger.warning("SystemsArchitect identified a dependency on 'README.md'. Adding a note to the LLM context about file access restrictions.")
            contextual_messages.append(
                HumanMessage(content="SYSTEM NOTE: The user's request requires information from 'README.md'. This file is part of the project's core documentation and is likely outside the sandboxed 'workspace' directory accessible to file system tools. Your plan should account for this. You can either proceed using general knowledge of a README's installation steps, or create a plan that first asks the user for the necessary text via the 'prompt_specialist'.")
            )

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
