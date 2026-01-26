# app/src/specialists/chat_specialist.py
"""
A foundational conversational specialist for general Q&A and chat interactions.
This specialist is designed to handle direct questions, provide information, and
engage in natural conversation when no specialized tool is needed.
"""
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)


class ChatSpecialist(BaseSpecialist):
    """
    A general-purpose conversational specialist for answering user questions
    and handling straightforward chat interactions.

    This specialist serves as the default fallback for conversational queries
    that don't require file I/O, code execution, or other specialized tools.
    It provides helpful, informative responses using natural language.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """
        Initializes the ChatSpecialist.

        Args:
            specialist_name: The name of this specialist instance (must match config.yaml key)
            specialist_config: Configuration dictionary from config.yaml
        """
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes the user's message and generates a conversational response.

        This method sends the full conversation history to the LLM to maintain
        context and generate a helpful, contextual response.

        Args:
            state: The current workflow state containing messages and other data

        Returns:
            Dictionary containing the new AI message to add to the conversation
        """
        logger.info(f"--- {self.specialist_name}: Processing chat request. ---")

        # Get messages with gathered_context injected (if Facilitator gathered any)
        messages = self._get_enriched_messages(state)

        # Check for uploaded image
        image_data = state.get("artifacts", {}).get("uploaded_image.png")

        # Create a standardized request with the full conversation history
        request = StandardizedLLMRequest(
            messages=messages,
            image_data=image_data
        )

        # Invoke the LLM adapter
        response_data = self.llm_adapter.invoke(request)

        # Extract the text response with fallback for None or missing values
        ai_response_content = response_data.get("text_response") or \
            "I apologize, but I'm unable to provide a response at this time."

        # Create a standardized AI message with LLM metadata
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=ai_response_content,
        )

        # Add the response to scratchpad for synthesis at the end
        logger.info(f"{self.specialist_name}: Response generated successfully.")

        return {
            "messages": [ai_message],
            "scratchpad": {
                "user_response_snippets": [ai_response_content]
            },
            "task_is_complete": True  # Chat responses are self-contained
        }
