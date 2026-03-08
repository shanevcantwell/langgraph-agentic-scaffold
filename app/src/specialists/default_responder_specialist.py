# app/src/specialists/default_responder_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class DefaultResponderSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, conversational response to the user's prompt.
    It is intended for simple, single-turn interactions where no other specialist's
    tools are required. It signals task completion after it runs.

    NOTE: This specialist is purely conversational - it does NOT inspect artifacts.
    Exit Interview logic (ADR-CORE-036) requires a dedicated graph node that can route.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"Initialized {self.specialist_name}")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response and signals that the task is complete.
        """
        # The DefaultResponder's role is purely conversational. It should only
        # consider the user's messages and its own previous responses to create a
        # clean conversational context, ignoring orchestration messages from other
        # specialists.
        messages: list[BaseMessage] = [
            msg for msg in state.get("messages", [])
            if isinstance(msg, HumanMessage) or (isinstance(msg, AIMessage) and msg.name == self.specialist_name)
        ]

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

        logger.info(f"DefaultResponderSpecialist generated response: '{text_response}'")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=text_response,
        )

        # Per the termination sequence, this specialist signals completion
        # by adding its final message and setting the `task_is_complete` flag.
        # #245: Write final_user_response.md so EndSpecialist skips LLM synthesis.
        # Terminal specialists produce self-contained responses — no synthesis needed.
        return {
            "messages": [ai_message],
            "task_is_complete": True,
            "artifacts": {"final_user_response.md": text_response},
            "scratchpad": {"user_response_snippets": [text_response]}
        }