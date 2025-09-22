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

        # Concatenate all snippets into a single string for the LLM to process.
        # The prompt for this specialist should instruct the LLM on how to combine these.
        combined_snippets = "\n\n---\n\n".join(str(s) for s in user_response_snippets)

        # Create a clean, minimal message list for the LLM. The system prompt (loaded
        # via the adapter) will guide the LLM, and we provide only the snippets
        # it needs to work on, avoiding the complexity of the full message history.
        messages = [
            HumanMessage(content=f"Please synthesize the following information into a single, coherent, user-facing response:\n\n{combined_snippets}")
        ]

        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)

        synthesized_response = response_data.get("text_response")
        if not synthesized_response:
            # If the LLM fails, log the issue and create a neutral placeholder.
            # The archiver will still capture the state for debugging, but we avoid
            # showing a technical error message to the end-user.
            logger.error(f"ResponseSynthesizer LLM failed. Raw output: {response_data.get('raw_response_content', 'N/A')}")
            synthesized_response = "I was unable to generate a final response based on the preceding actions."

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