# src/specialists/prompt_specialist.py
import logging
from typing import Dict, Any, List
from langchain_core.messages import AIMessage, BaseMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class PromptSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, text-based response to the user's prompt
    or the current state of the conversation. It does not use tools.
    """

    def __init__(self, specialist_name: str):
        """Initializes the PromptSpecialist."""
        super().__init__(specialist_name=specialist_name)

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response based on the message history.
        """
        messages: List[BaseMessage] = state["messages"]

        if not messages:
            return {"messages": [AIMessage(content="I have no input to respond to.")]}

        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)
        ai_response_content = response_data.get("text_response", "I am unable to provide a response at this time.")

        new_message = AIMessage(content=ai_response_content)
        
        # CORRECTED: Return only the new message (the delta).
        # LangGraph will handle appending it to the list, preventing duplication.
        return {"messages": [new_message]}
