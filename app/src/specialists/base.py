# src/specialists/base.py

from abc import ABC, abstractmethod
from typing import List, Optional, Any, Dict

from ..graph.state import GraphState
from ..llm.factory import LLMClientFactory
from ..llm.clients import BaseLLMClient
from langchain_core.messages import BaseMessage, AIMessage, SystemMessage, HumanMessage

class BaseSpecialist(ABC):
    """
    An abstract base class that defines the standard interface for all specialist
    agents. It now includes an integrated LLM client instantiated via a factory.
    """

    def __init__(
        self,
        system_prompt: str,
        llm_provider: str,
        tools: Optional[List[Any]] = None
    ):
        """
        Initializes the specialist.

        Args:
            system_prompt (str): The system prompt that defines the specialist's persona.
            llm_provider (str): The name of the LLM provider to use (e.g., 'gemini', 'ollama').
            tools (Optional[List[Any]]): An optional list of tools for the specialist.
        """
        self.system_prompt_content = system_prompt
        self.tools = tools if tools is not None else []
        self.llm_client: BaseLLMClient = LLMClientFactory.create_client(llm_provider)

    def invoke(self, state: GraphState) -> Dict[str, Any]:
        """
        The main entry point for the specialist's logic. This implementation
        handles the core LLM call cycle. Concrete classes can override this
        or parts of it if more complex logic (like tool use) is needed.

        Args:
            state (GraphState): The current state of the graph.

        Returns:
            Dict[str, Any]: A dictionary with the state update.
        """
        print(f"---INVOKING SPECIALIST (Provider: {self.llm_client.__class__.__name__})---")
        
        # 1. Prepare messages for the LLM
        messages_to_send = [SystemMessage(content=self.system_prompt_content)]
        messages_to_send.extend(state["messages"])

        # 2. Call the LLM via the standardized client interface
        ai_response = self.llm_client.invoke(messages_to_send)

        # 3. Return the response in the format expected by the graph state
        return {"messages": [ai_response]}

    @abstractmethod
    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        The execution method called by the LangGraph node.
        For most simple specialists, this can just call self.invoke().
        """
        pass
