import logging
from typing import Dict, Any

from .base import BaseSpecialist
from ..enums import Specialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt
from langchain_core.messages import HumanMessage
from google.generativeai.types import FunctionDeclaration, Tool

logger = logging.getLogger(__name__)

class RouterSpecialist(BaseSpecialist):
    """
    A specialist that routes the user's request to the appropriate specialist
    by leveraging the LLM's tool-calling capabilities as a structured output mechanism.
    """

    def __init__(self):
        super().__init__(specialist_name="router_specialist")
        logger.info(f"Initialized {self.__class__.__name__}.")

    def execute(self, state: dict) -> Dict[str, Any]:
        """
        Invokes the LLM with the decoy tool to get a structured routing decision.
        """
        logger.info("Executing Router...")
        user_prompt = state['messages'][-1].content
        system_prompt = load_prompt("router_specialist_prompt.md")

        # Define the "Decoy Tool" schema. This is our hard contract.
        # The enum provides a strict list of valid choices.
        routing_tool = Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="route_to_specialist",
                    description="Routes the request to the appropriate specialist.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "next_specialist": {
                                "type": "STRING",
                                "description": "The name of the specialist to route to.",
                                "enum": [s.value for s in Specialist]
                            }
                        },
                        "required": ["next_specialist"]
                    }
                )
            ]
        )

        request = StandardizedLLMRequest(
            messages=[
                HumanMessage(content=user_prompt),
            ],
            system_prompt_content=system_prompt,
            tools=[routing_tool]
        )

        response_data = self.llm_adapter.invoke(request)
        
        next_specialist = response_data.get("next_specialist")

        if next_specialist and next_specialist in {s.value for s in Specialist}:
            logger.info(f"Router decision: Routing to {next_specialist}")
            return {"next_specialist": next_specialist}
        else:
            logger.error(f"Router returned an invalid specialist: {next_specialist}. Routing to PROMPT specialist for clarification.\n")
            return {"next_specialist": Specialist.PROMPT.value}
