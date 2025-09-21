# app/src/specialists/default_responder_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage

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
        messages = state["messages"]
        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)
        text_response = response_data.get("text_response", "I am unable to provide a response.")
        logger.info(f"DefaultResponderSpecialist generated response: '{text_response}'")
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=text_response,
        )
        # This specialist's task is considered complete after one turn.
        # By setting `task_is_complete`, we trigger the Three-Stage Termination
        # pattern, ensuring the response_synthesizer and archiver run.
        return {"messages": [ai_message], "task_is_complete": True}