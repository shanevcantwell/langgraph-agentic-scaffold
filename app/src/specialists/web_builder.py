import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas import WebContent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    """
    A specialist that generates a self-contained HTML document based on a
    system_plan artifact in the state.
    """
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)
        logger.info("---INITIALIZED WebBuilder---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        system_plan = state.get("system_plan")
        if not system_plan:
            raise ValueError("WebBuilder Error: 'system_plan' not found in state.")

        # --- Iteration Control ---
        # Default to 1 cycle (current behavior) if not specified in the plan.
        refinement_cycles = system_plan.get("refinement_cycles", 1)
        current_iteration = state.get("web_builder_iteration", 0)
        
        logger.info(f"Executing WebBuilder iteration {current_iteration + 1} of {refinement_cycles}.")

        # --- Contextual Prompting ---
        messages: List[BaseMessage] = state["messages"]
        current_html = state.get("html_artifact")
        text_to_process = state.get("text_to_process")
        
        contextual_messages = messages[:] # Make a copy

        # If there's text in the state, add it as primary context for building the page.
        # This ensures the generated HTML uses the content from the file.
        if text_to_process:
            contextual_messages.append(HumanMessage(
                content=f"Use the following text as the primary content and context for building the webpage:\n\n---\n{text_to_process}\n---"
            ))

        # If we have existing HTML and this is a refinement cycle, add it to the context.
        if current_html and current_iteration > 0:
            refinement_prompt = HumanMessage(
                content=f"This is refinement cycle {current_iteration + 1} of {refinement_cycles}. Please review and improve the following HTML based on the original plan and content.\n\n```html\n{current_html}\n```"
            )
            contextual_messages.append(refinement_prompt)

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=WebContent
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("WebBuilder failed to get a valid JSON response from the LLM.")

        web_content = WebContent(**json_response)
        next_iteration = current_iteration + 1

        # --- Prepare state update ---
        updated_state = {
            "messages": [AIMessage(content=f"Completed HTML generation/refinement cycle {next_iteration}.", name=self.specialist_name)],
            "html_artifact": web_content.html_document,
            "web_builder_iteration": next_iteration
        }

        if next_iteration >= refinement_cycles:
            logger.info(f"WebBuilder has completed all {refinement_cycles} refinement cycles. Signaling task completion.")
            updated_state["task_is_complete"] = True
            updated_state["web_builder_iteration"] = None # Clean up the counter from the state
        else:
            # More iterations to go. Loop back to self via the router.
            logger.info(f"Recommending 'web_builder' for next refinement cycle.")
            updated_state["recommended_specialists"] = ["web_builder"]

        return updated_state
