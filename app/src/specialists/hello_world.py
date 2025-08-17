# src/agents/hello_world.py

import logging
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any

from .base import SpecialistNode
from ..graph.state import GraphState

logger = logging.getLogger(__name__)

class HelloWorldSpecialist(SpecialistNode):
    """
    A concrete implementation of a specialist that greets the user.
    This class demonstrates how to inherit from SpecialistNode.
    """

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Executes the specialist's logic.
        """
        logger.info("---CALLING HELLO WORLD SPECIALIST (CLASS)---")
        
        last_message = state["messages"][-1]
        user_request = last_message.content
        
        response_content = f"Hello from the class-based specialist! You said: '{user_request}'"

        new_message = AIMessage(content=response_content)
        return {"messages": [new_message]}
