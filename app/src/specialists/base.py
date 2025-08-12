# src/specialists/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, BaseMessage, AIMessage
from ..graph.state import GraphState
from ..llm.factory import LLMClientFactory

class BaseSpecialist(ABC):
    """
    Abstract base class for all specialists in the multi-agent system.
    """

    def __init__(self, system_prompt: str, llm_provider: str, tools: Optional[List] = None):
        self.system_prompt_content = system_prompt
        self.llm_client = LLMClientFactory.create_client(llm_provider)
        self.tools = tools if tools is not None else []
        print(f"---INITIALIZED BASE ({self.__class__.__name__})---")

    def invoke(self, state: GraphState) -> Dict[str, Any]:
        """
        Prepares messages and invokes the LLM client. This is a standard
        implementation that can be used by most specialists.

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
        ai_response = self.llm_client.invoke(messages_to_send, tools=self.tools)

        # 3. Return the response in the format expected by the graph state
        return {"messages": [ai_response]}

    def _parse_llm_response(self, response_dict: Dict[str, Any]) -> str:
        """
        Parses the dictionary returned by self.invoke() to extract the LLM's
        string content. This is a robust helper method for subclasses.

        Args:
            response_dict (Dict[str, Any]): The dictionary returned by the invoke method.

        Returns:
            str: The content of the AI message, or an empty string if not found.
        """
        if not isinstance(response_dict, dict) or "messages" not in response_dict:
            return ""
        
        messages = response_dict["messages"]
        if not isinstance(messages, list) or not messages:
            return ""

        # The most recent message from the LLM is the one we want.
        last_message = messages[0]
        if hasattr(last_message, 'content'):
            return last_message.content
        
        return ""

    @abstractmethod
    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        The execution method called by the LangGraph node.
        For most simple specialists, this can just call self.invoke().
        """
        pass

