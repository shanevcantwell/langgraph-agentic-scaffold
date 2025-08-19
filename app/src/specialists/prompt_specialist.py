import logging
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class PromptSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__(specialist_name="prompt_specialist")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        logger.info("---EXECUTING PROMPT SPECIALIST---")
        
        user_prompt_message = state['messages'][-1]
        
        if not isinstance(user_prompt_message, HumanMessage):
            raise ValueError("PromptSpecialist requires the last message in the state to be a HumanMessage.")

        request = StandardizedLLMRequest(
            messages=[user_prompt_message],
        )

        response_data = self.llm_adapter.invoke(request)

        return {"messages": [AIMessage(content=str(response_data))]}