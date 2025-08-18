# src/specialists/prompt_specialist.py

import logging
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class PromptSpecialist(BaseSpecialist):
    """
    A concrete specialist that takes a user's prompt directly from the graph
    state, sends it to the configured LLM, and returns the response.

    This is a fundamental building block for direct Q&A and instruction-following.
    """

    def __init__(self):
        """
        Initializes the PromptSpecialist.
        """
        super().__init__(specialist_name="prompt_specialist")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: dict) -> Dict[str, Any]:
        """
        The execution entry point called by the LangGraph node.

        It extracts the latest user message as the prompt, invokes the LLM,
        and returns the AI's response to be appended to the message history.

        Args:
            state (dict): The current state of the graph.

        Returns:
            Dict[str, Any]: A dictionary with the 'messages' key containing the
                            AI's response.
        """
        logger.info("---EXECUTING PROMPT SPECIALIST---")
        
        user_prompt_message = state['messages'][-1]
        
        if not isinstance(user_prompt_message, HumanMessage):
            raise ValueError("PromptSpecialist requires the last message in the state to be a HumanMessage.")

        system_prompt = load_prompt("prompt_specialist_prompt.md")

        request = StandardizedLLMRequest(
            messages=[user_prompt_message],
            system_prompt_content=system_prompt,
        )

        response_data = self.llm_adapter.invoke(request)

        return {"messages": [AIMessage(content=response_data)]}
