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
        print(f"---INITIALIZED {self.__class__.__name__}---")

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

        # The prompt for this specialist should specify a JSON output.
        ai_response_str = self.llm_client.invoke(messages_to_send).content.strip()
        next_specialist = None
        response_json = {}

        extracted_json_str = ""
        # Attempt to find JSON within markdown code fences
        if "```json" in ai_response_str:
            start_index = ai_response_str.find("```json") + len("```json")
            end_index = ai_response_str.find("```", start_index)
            if start_index != -1 and end_index != -1:
                extracted_json_str = ai_response_str[start_index:end_index].strip()
        
        # If no markdown JSON, try to parse the whole string
        if not extracted_json_str:
            extracted_json_str = ai_response_str

        try:
            # Attempt to parse as JSON first
            parsed_response = json.loads(extracted_json_str)
            if isinstance(parsed_response, dict):
                next_specialist = parsed_response.get("next_specialist")
            elif isinstance(parsed_response, str):
                # If JSON parsing results in a string, use it directly
                next_specialist = parsed_response
            else:
                print(f"---ROUTER WARNING: LLM response parsed to unexpected type: {type(parsed_response)}. Response: \"{ai_response_str}\"---")

        except json.JSONDecodeError:
            # If not valid JSON, try to extract a raw string and treat it as the specialist name
            print(f"---ROUTER WARNING: LLM response is not valid JSON. Attempting to parse as raw string. Response: \"{ai_response_str}\"---")
            next_specialist = ai_response_str.strip('"` \n')

        # Validate the final decision.
        valid_specialists = {s.value for s in Specialist}
        if next_specialist and next_specialist in valid_specialists:
            print(f"---ROUTER DECISION: {next_specialist}---")
            return {"next_specialist": next_specialist}
        else:
            # If no valid specialist was found, default to the prompt specialist.
            error_msg = f"Router could not determine a valid specialist. LLM Response: '{ai_response_str}'. Parsed as: '{next_specialist}'"
            print(f"---ROUTER ERROR: {error_msg}. Routing to PROMPT specialist for clarification.---")
            return {"next_specialist": Specialist.PROMPT.value}
