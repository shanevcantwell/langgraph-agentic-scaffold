# app/src/specialists/prompt_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class PromptSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, conversational response to the user's prompt.
    It is intended for simple, single-turn interactions where no other specialist's
    tools are required. It signals task completion after it runs.
    """
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response and signals that the task is complete.
        """
        messages = state["messages"]
        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)
        text_response = response_data.get("text_response", "I am unable to provide a response.")
        logger.info(f"PromptSpecialist generated response: '{text_response}'")
        return {"messages": [AIMessage(content=text_response)], "task_is_complete": True}
