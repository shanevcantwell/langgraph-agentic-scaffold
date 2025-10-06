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
        raw_snippets = scratchpad.get("user_response_snippets", [])

        # Filter out any empty or whitespace-only snippets before processing.
        user_response_snippets = [s for s in raw_snippets if str(s).strip()]

        # Guard clause: If there are no snippets, do not call the LLM.
        # Instead, provide a generic but safe completion message. This prevents
        # the LLM from hallucinating on an empty prompt.
        if not user_response_snippets and "final_user_response.md" not in state.get("artifacts", {}):
            logger.warning(f"{self.specialist_name}: No user_response_snippets found. Providing a default completion message.")
            synthesized_response = "The workflow has completed its tasks, but no specific output was generated to display."
            # Skip directly to artifact creation
        else:
            # Concatenate all snippets into a single string for the LLM to process.
            # The prompt for this specialist should instruct the LLM on how to combine these.
            combined_snippets = "\n\n---\n\n".join(str(s) for s in user_response_snippets)

            # Create a clean, minimal message for the LLM. The system prompt (loaded
            # by the adapter) contains all the instructions. We just need to provide
            # the raw data to be synthesized.
            messages = [
                HumanMessage(content=combined_snippets)
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