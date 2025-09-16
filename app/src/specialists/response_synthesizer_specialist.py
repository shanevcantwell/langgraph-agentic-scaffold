# app/src/specialists/response_synthesizer_specialist.py
from typing import Dict, Any
import logging
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .helpers import create_llm_message

logger = logging.getLogger(__name__)

class ResponseSynthesizerSpecialist(BaseSpecialist):
    """
    A specialist that synthesizes a final, user-facing response from a
    collection of text snippets accumulated during the workflow.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> dict:
        """
        Takes the list of strings from state['user_response'], combines them,
        and uses an LLM to generate a polished, final summary.
        """
        user_response_snippets = state.get("user_response", [])

        # If there are no snippets to synthesize, perform no action.
        if not user_response_snippets or not isinstance(user_response_snippets, list):
            logger.info("No user response snippets to synthesize. Skipping.")
            return {}

        # Combine the snippets into a single block of text for the LLM.
        combined_snippets = "\n\n".join(f"- {snippet}" for snippet in user_response_snippets)

        # The system prompt for this specialist will instruct it to synthesize.
        # We just need to provide the raw data.
        synthesis_prompt = f"""
Here are the key findings and actions taken during the process:

{combined_snippets}

Please synthesize these points into a single, clear, and friendly response for the end-user.
"""

        request = StandardizedLLMRequest(
            messages=[("human", synthesis_prompt)]
        )

        response_data = self.llm_adapter.invoke(request)
        synthesized_content = response_data.get("text_response", "I have completed the task.")

        # Create a final AI message for the history to maintain full traceability.
        final_message = create_llm_message(self.specialist_name, self.llm_adapter, synthesized_content)

        # Per ADR-004, this specialist signals completion.
        # It overwrites the `user_response` field with the final string (not a list)
        # for easier consumption by clients. It also places the final response in
        # the `artifacts` dictionary, adhering to the "Future-Proof Your State
        # Management" best practice from CREATING_A_NEW_SPECIALIST.md.
        return {
            "messages": [final_message],
            "user_response": synthesized_content,
            "artifacts": {"final_user_response.md": synthesized_content},
            "task_is_complete": True
        }