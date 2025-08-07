# src/specialists/prompt_specialist.py

from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..utils.prompt_loader import load_prompt
from ..graph.state import GraphState


class PromptSpecialist(BaseSpecialist):
    """
    A concrete specialist that takes a user's prompt directly from the graph
    state, sends it to the configured LLM, and returns the response.

    This is a fundamental building block for direct Q&A and instruction-following.
    """

    def __init__(self, llm_provider: str):
        """
        Initializes the PromptSpecialist.

        It uses a generic system prompt that can be overridden if needed,
        but its primary purpose is to be a direct conduit to the LLM.

        Args:
            llm_provider (str): The LLM provider to use ('gemini', 'ollama', etc.).
        """
        system_prompt = load_prompt("prompt_specialist")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        print(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        The execution entry point called by the LangGraph node.

        It extracts the latest user message as the prompt, invokes the LLM,
        and returns the AI's response to be appended to the message history.

        Args:
            state (GraphState): The current state of the graph.

        Returns:
            Dict[str, Any]: A dictionary with the 'messages' key containing the
                            AI's response.
        """
        print("---EXECUTING PROMPT SPECIALIST---")
        
        # For this simple specialist, we assume the last message is the user's prompt.
        # A more robust implementation might look for a specific key in the state.
        user_prompt_message = state['messages'][-1]
        
        if not isinstance(user_prompt_message, HumanMessage):
            raise ValueError("PromptSpecialist requires the last message in the state to be a HumanMessage.")

        # We don't use the base class's `invoke` because we want a fresh conversation
        # with only the system prompt and the current user prompt.
        messages_to_send = [
            SystemMessage(content=self.system_prompt_content),
            user_prompt_message
        ]

        ai_response = self.llm_client.invoke(messages_to_send)

        return {"messages": [ai_response]}
