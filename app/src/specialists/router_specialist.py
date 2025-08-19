import logging
from typing import Dict, Any

from .base import BaseSpecialist
from ..enums import Specialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage
from google.generativeai.types import FunctionDeclaration, Tool

logger = logging.getLogger(__name__)

class RouterSpecialist(BaseSpecialist):
    def __init__(self):
        super().__init__(specialist_name="router_specialist")
        logger.info(f"Initialized {self.__class__.__name__}.")

    def execute(self, state: dict) -> Dict[str, Any]:
        logger.info("Executing Router...")

        # --- FIX STARTS HERE ---
        # Create a concise summary of the current state for the router's context.
        # This is more robust than just looking at the last message.
        state_summary = f"The user's initial goal is: '{state['messages'][0].content}'"
        if state.get("json_artifact"):
            state_summary += "\nA JSON artifact (blueprint) has ALREADY been created by the Systems Architect. The next step should be a 'builder'."
        else:
            state_summary += "\nNo JSON artifact (blueprint) exists yet. A plan needs to be created first."
        
        logger.info(f"Router state summary: {state_summary}")
        # The user_prompt is now this rich summary.
        user_prompt = state_summary
        # --- FIX ENDS HERE ---

        routing_tool = Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="route_to_specialist",
                    description="Selects the next specialist based on a multi-step workflow. For any new creation task (like making a webpage or diagram), the first step MUST be the 'systems_architect'.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "next_specialist": {
                                "type": "STRING",
                                "description": "The specialist to route to. CRITICAL: If a JSON artifact already exists, choose 'web_builder'. If not, choose 'systems_architect'.",
                                "enum": [s.value for s in Specialist]
                            }
                        },
                        "required": ["next_specialist"]
                    }
                )
            ]
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=user_prompt)],
            tools=[routing_tool]
        )

        llm_response = self.llm_adapter.invoke(request)
        
        tool_calls = llm_response.get("tool_calls")
        next_specialist = None

        if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
            first_tool_call = tool_calls[0]
            if first_tool_call.get("name") == "route_to_specialist":
                next_specialist = first_tool_call.get("args", {}).get("next_specialist")

        if next_specialist and next_specialist in {s.value for s in Specialist}:
            logger.info(f"Router decision: Routing to {next_specialist}")
            return {"next_specialist": next_specialist}
        else:
            logger.error(f"Router returned an invalid or no specialist: {next_specialist}. Routing to PROMPT specialist for clarification.\n")
            return {"next_specialist": Specialist.PROMPT.value}