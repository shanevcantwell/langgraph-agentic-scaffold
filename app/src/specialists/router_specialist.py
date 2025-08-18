import logging
import json
from typing import Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt
from ..enums import Specialist
from ..llm.clients import LLMInvocationError

logger = logging.getLogger(__name__)

class RouterSpecialist(BaseSpecialist):
    """
    A specialist that routes the user's request to the appropriate specialist
    by leveraging the LLM's tool-calling capabilities as a structured output mechanism.
    """

    def __init__(self, llm_provider: str):
        system_prompt = load_prompt("router_specialist")
        
        # Define the "Decoy Tool" schema. This is our hard contract.
        # The enum provides a strict list of valid choices.
        routing_tool = {
            "name": "route_to_specialist",
            "description": "Routes the request to the appropriate specialist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "next_specialist": {
                        "type": "string",
                        "description": "The name of the specialist to route to.",
                        "enum": [s.value for s in Specialist]
                    }
                },
                "required": ["next_specialist"]
            }
        }
        
        # Pass the tool definition to the base class
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider, tools=[routing_tool])
        logger.info(f"Initialized {self.__class__.__name__} with routing tool.")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Invokes the LLM with the decoy tool to get a structured routing decision.
        """
        logger.info("Executing Router...")
        user_prompt_message = state['messages'][-1]
        messages_to_send = [
            SystemMessage(content=self.system_prompt_content),
            user_prompt_message,
        ]

        try:
            # Invoke the client, passing the tools defined in __init__
            # The client will now handle the tool call response.
            response_data = self.llm_client.invoke(messages_to_send, tools=self.tools)
            
            # The client now returns the arguments of the tool call directly.
            next_specialist = response_data.get("next_specialist")

            if next_specialist and next_specialist in {s.value for s in Specialist}:
                logger.info(f"Router decision: Routing to {next_specialist}")
                return {"next_specialist": next_specialist}
            else:
                raise LLMInvocationError(f"Router returned an invalid specialist: {next_specialist}")

        except LLMInvocationError as e:
            error_msg = f"Router failed to determine a valid specialist: {e}"
            logger.error(f"{error_msg}. Routing to PROMPT specialist for clarification.")
            return {"next_specialist": Specialist.PROMPT.value}
