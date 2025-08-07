# src/specialists/router_specialist.py

import json
from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage

from .base import BaseSpecialist
from ..graph.state import GraphState
from ..utils.prompt_loader import load_prompt
from ..enums import Specialist

class RouterSpecialist(BaseSpecialist):
    """
    A specialist that routes the user's request to the appropriate specialist.
    It analyzes the user's prompt and decides which specialist is best suited
    to handle it.
    """

    def __init__(self, llm_provider: str):
        # Adheres to the DEVELOPERS_GUIDE.md contract for creating a new specialist.
        # The specialist name is hardcoded here to match its corresponding prompt file.
        system_prompt = load_prompt("router_specialist")
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        print("---INITIALIZED ROUTER SPECIALIST---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Analyzes the user prompt and routes to the appropriate specialist.
        Input: state['messages'] must contain the user prompt.
        Output: A dictionary with 'next_specialist' key for routing.
        """
        print("---EXECUTING ROUTER---")
        user_prompt_message = state['messages'][-1]

        messages_to_send = [
            SystemMessage(content=self.system_prompt_content),
            user_prompt_message,
        ]

        # The prompt for this specialist MUST specify a JSON output with a "next_specialist" key.
        ai_response_str = self.llm_client.invoke(messages_to_send).content

        try:
            # Per the DEVELOPERS_GUIDE, the response must be JSON.
            response_json = json.loads(ai_response_str)
            next_specialist = response_json.get("next_specialist")

            if not next_specialist:
                raise ValueError("JSON response missing 'next_specialist' key.")

            # Validate that the specialist is a known one.
            valid_specialists = [s.value for s in Specialist]
            if next_specialist not in valid_specialists:
                raise ValueError(f"Router returned an unknown specialist: {next_specialist}")

            print(f"---ROUTER DECISION: {next_specialist}---")
            return {"next_specialist": next_specialist}

        except (json.JSONDecodeError, ValueError) as e:
            print(f"---ROUTER ERROR: {e}. Routing to PROMPT specialist for clarification.---")
            return {"next_specialist": Specialist.PROMPT.value}
