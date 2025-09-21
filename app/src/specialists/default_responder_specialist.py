# app/src/specialists/default_responder_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage

from ..graph.state import ScratchpadUpdate
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class DefaultResponderSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, conversational response to the user's prompt.
    It is intended for simple, single-turn interactions where no other specialist's
    tools are required. It signals task completion after it runs.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"Initialized {self.specialist_name}")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response and signals that the task is complete.
        """
        # The DefaultResponder's role is purely conversational. It should not be
        # influenced by tool calls from previous orchestration steps (like Triage).
        # We create a "clean" message history by removing tool_calls from any
        # previous AI messages to ensure the LLM operates in a conversational mode.
        messages: list[BaseMessage] = []
        for msg in state.get("messages", []):
            if isinstance(msg, AIMessage) and msg.tool_calls:
                # Create a new AIMessage without the tool_calls
                cleaned_msg = AIMessage(content=msg.content, name=msg.name)
                messages.append(cleaned_msg)
            else:
                messages.append(msg)
        
        # The specialist should act on the full, current state of the conversation.
        # Its system prompt guides it to focus on the most recent message.
        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)

        text_response = response_data.get("text_response")
        if not text_response:
            # If the LLM fails to provide a text response, provide a more informative fallback.
            raw_response_content = response_data.get("raw_response_content", "No raw response available.")
            error_message = f"I was unable to provide a response. The LLM returned an empty text response. Raw output: {raw_response_content}"
            text_response = error_message

        logger.info(f"DefaultResponderSpecialist generated response snippet: '{text_response}'")

        # Get the current snippets and append the new one. This ensures we don't
        # overwrite snippets from previous specialists. The `operator.ior` on the
        # GraphState's scratchpad will merge this update correctly.
        current_snippets = state.get("scratchpad", {}).get("user_response_snippets", [])
        new_snippets = current_snippets + [text_response]

        # Per the Three-Stage Termination pattern, this specialist signals completion
        # and provides its output as a snippet for the ResponseSynthesizer.
        # It does NOT add a message to the main history, as the synthesizer is
        # responsible for the final, consolidated user-facing message.
        return {
            "task_is_complete": True,
            "scratchpad": ScratchpadUpdate(user_response_snippets=[text_response]),
            "scratchpad": {"user_response_snippets": new_snippets},
        }