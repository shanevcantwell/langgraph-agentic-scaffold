# src/agents/hello_world.py

import logging
from langchain_core.messages import AIMessage, HumanMessage
from typing import Dict, Any

from .base import BaseSpecialist
from ..graph.state import GraphState

logger = logging.getLogger(__name__)

class HelloWorldSpecialist(BaseSpecialist):
    """
    A concrete implementation of a specialist that greets the user.
    This class demonstrates how to inherit from BaseSpecialist.
    """

    def _execute_logic(self, state: GraphState) -> Dict[str, Any]:
        """
        Executes the specialist's logic.
        """
        logger.info("---CALLING HELLO WORLD SPECIALIST (CLASS)---")
        
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            user_request = last_message.content
        else:
            user_request = "you said nothing"
        
        response_content = f"Hello from the class-based specialist! You said: '{user_request}'"

        new_message = AIMessage(content=response_content)
        return {"messages": [new_message]}
