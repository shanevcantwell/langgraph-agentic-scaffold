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

    def __init__(self):
        """Initializes the PromptSpecialist."""
        super().__init__(specialist_name="prompt_specialist")
        logger.info("---INITIALIZED PromptSpecialist---")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a text response based on the message history.
        """
        messages: List[BaseMessage] = state["messages"]

        if not messages:
            return {"messages": state.get("messages", []) + [AIMessage(content="I have no input to respond to.")]}

        # Create a standardized request to the Language Model.
        # Crucially, we do NOT pass any tools here. This specialist's job
        # is to generate text content, not to call functions.
        request = StandardizedLLMRequest(messages=messages)

        # Invoke the LLM adapter.
        response_data = self.llm_adapter.invoke(request)

        # The adapter will return a 'text_response' when not in tool-calling mode.
        ai_response_content = response_data.get("text_response", "I am unable to provide a response at this time.")

        new_message = AIMessage(content=ai_response_content)
        return {"messages": state["messages"] + [new_message]}