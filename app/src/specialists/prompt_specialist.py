# app/src/specialists/prompt_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class PromptSpecialist(BaseSpecialist):
    """
    A specialist that generates a direct, conversational response to the user's prompt.
    """
    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Get enriched messages (includes gathered_context if available)
        messages = self._get_enriched_messages(state)
        if not messages:
            logger.warning("PromptSpecialist called with no messages. Returning empty response.")
            return {"messages": [create_llm_message(self.specialist_name, self.llm_adapter, "I have nothing to respond to.")]}

        request = StandardizedLLMRequest(messages=messages)
        response_data = self.llm_adapter.invoke(request)
        text_response = response_data.get("text_response", "I am unable to provide a response.")
        logger.info(f"PromptSpecialist generated response: '{text_response}'")
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=text_response,
        )
        return {"messages": [ai_message]}
