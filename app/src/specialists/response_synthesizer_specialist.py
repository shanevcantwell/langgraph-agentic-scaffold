# app/src/specialists/response_synthesizer_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)


class ResponseSynthesizerSpecialist(BaseSpecialist):
    """
    An LLM-driven specialist that synthesizes a final, coherent, user-facing
    response from a collection of text snippets. This is a core part of the
    standard termination sequence.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Synthesizes a final response from snippets in the scratchpad and stores
        the result as an artifact.
        """
        logger.info(f"--- {self.specialist_name}: Synthesizing final response. ---")

        scratchpad = state.get("scratchpad", {})
        user_response_snippets = scratchpad.get("user_response_snippets", [])

        if not user_response_snippets:
            logger.warning(f"No 'user_response_snippets' found in scratchpad for {self.specialist_name} to synthesize. Skipping.")
            # If nothing to synthesize, just pass through to the next stage (Archiver)
            return {
                "artifacts": {
                    "final_user_response.md": "No specific user-facing response was synthesized."
                }
            }

        # Concatenate all snippets into a single string for the LLM to process.
        # The prompt for this specialist should instruct the LLM on how to combine these.
        combined_snippets = "\n\n---\n\n".join(map(str, user_response_snippets))

        # Create a message for the LLM. The system prompt (loaded via config)
        # will guide the LLM on how to synthesize these.
        messages = state["messages"] + [
            HumanMessage(content=f"Please synthesize the following information into a single, coherent response for the user:\n\n{combined_snippets}")
        ]

        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)

        synthesized_response = response_data.get("text_response")
        if not synthesized_response:
            # If the LLM fails to provide a text response, provide a more informative fallback.
            raw_response_content = response_data.get("raw_response_content", "No raw response available.")
            error_message = f"I was unable to synthesize a coherent response. The LLM returned an empty text response. Raw output: {raw_response_content}"
            synthesized_response = error_message

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=synthesized_response,
            additional_kwargs={"synthesized_from_snippets": True}
        )

        # Store the synthesized response as an artifact for the Archiver.
        # Clear the snippets from the scratchpad as they have been processed.
        return {
            "messages": [ai_message],
            "artifacts": {"final_user_response.md": synthesized_response},
            "scratchpad": {
                "user_response_snippets": [] # Clear the snippets after synthesis
            }
        }