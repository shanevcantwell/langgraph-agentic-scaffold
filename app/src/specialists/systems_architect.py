import logging
import os
from typing import Dict, Any

from .base import BaseSpecialist
from ..graph.state import GraphState

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    """
    A specialist that generates Mermaid.js code from a high-level goal.
    """
    def __init__(self, llm_provider: str):
        # Load the system prompt from the dedicated file for better separation of concerns.
        prompt_path = os.path.join(os.path.dirname(__file__), "../../prompts/systems_architect_prompt.md")
        with open(prompt_path, 'r') as f:
            system_prompt = f.read()
        
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Generates the Mermaid code and updates the state.
        This method now correctly uses the base class's parsing helper.
        """
        logger.info("SYSTEMS ARCHITECT: Generating Mermaid Code")
        
        # 1. Invoke the LLM. This returns a dictionary formatted for state updates,
        #    e.g., {'messages': [AIMessage(content="...")]}
        llm_response_dict = self.invoke(state)
        
        # 2. Use the robust parser from the base class to safely extract the string content.
        json_artifact = self._parse_llm_response(llm_response_dict)
        
        if not json_artifact:
            # This is a safeguard in case the LLM response was empty or malformed.
            logger.warning("SYSTEMS ARCHITECT: FAILED to parse LLM response.")

        logger.info(f"SYSTEMS ARCHITECT: Generated JSON Artifact\n{json_artifact[:250]}...")

        # 3. Prepare the final dictionary to update the graph's state.
        # We take the original response dictionary (which contains the new message for the history)
        # and add the 'json_artifact' key to it.
        final_state_update = llm_response_dict.copy()
        final_state_update["json_artifact"] = json_artifact
        
        return final_state_update
