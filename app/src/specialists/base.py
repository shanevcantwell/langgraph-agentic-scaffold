import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, BaseMessage, AIMessage
from ..graph.state import GraphState
from ..llm.factory import LLMClientFactory

logger = logging.getLogger(__name__)

class BaseSpecialist(ABC):
    """
    Abstract base class for all specialists in the multi-agent system.
    """

    def __init__(self, system_prompt: str, llm_provider: str, tools: Optional[List] = None):
        self.system_prompt_content = system_prompt
        # MODIFIED: Pass the system_prompt to the factory for correct client initialization
        self.llm_client = LLMClientFactory.create_client(
            provider=llm_provider,
            system_prompt=system_prompt
        )
        self.tools = tools if tools is not None else []
        logger.info(f"---INITIALIZED BASE ({self.__class__.__name__})---")

    def invoke(self, state: GraphState) -> Dict[str, Any]:
        """
        Prepares messages and invokes the LLM client. This is a standard
        implementation that can be used by most specialists.
        """
        logger.info(f"---INVOKING SPECIALIST (Provider: {self.llm_client.__class__.__name__})---")
        
        # MODIFIED: The system prompt is no longer added here.
        # It is now part of the client's configuration.
        messages_to_send = state["messages"]

        try:
            # The client's invoke signature is now simpler
            ai_response = self.llm_client.invoke(messages_to_send, tools=self.tools)
            return {"messages": [AIMessage(content=str(ai_response))]}
        except Exception as e:
            import traceback
            error_message = f"Error invoking LLM client: {e}"
            detailed_error = traceback.format_exc()
            logger.error(f"{error_message}\n{detailed_error}")
            return {"error": error_message, "error_details": detailed_error}

    @abstractmethod
    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        The execution method called by the LangGraph node.
        """
        pass
