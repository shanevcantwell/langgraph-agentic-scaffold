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
        print("---SYSTEMS ARCHITECT: Generating JSON Artifact---") # FIX: Consistent logging
        llm_response_dict = self.invoke(state)
        json_artifact = self._parse_llm_response(llm_response_dict)
        if not json_artifact or "Error:" in json_artifact: # FIX: Better error handling
            print(f"---SYSTEMS ARCHITECT: FAILED to generate valid JSON...")
            json_artifact = '{"error": "Failed to generate JSON artifact from LLM."}'
            logger.info(f"SYSTEMS ARCHITECT: Generated JSON Artifact\n{json_artifact[:250]}...")

            # 3. Prepare the final dictionary to update the graph's state.
            # We take the original response dictionary (which contains the new message for the history)
            # and add the 'json_artifact' key to it.
            final_state_update = llm_response_dict.copy()
            final_state_update["json_artifact"] = json_artifact
            
            return final_state_update
