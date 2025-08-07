# src/specialists/data_extractor_specialist.py

import json
from typing import Dict, Any

# Principle #1 In Action: Importing the prompt loader
from ..utils.prompt_loader import load_prompt
from .base import BaseSpecialist
from ..graph.state import GraphState
from langchain_core.messages import SystemMessage, HumanMessage

# Principle #2 In Action: The class name 'DataExtractorSpecialist' matches
# the filename 'data_extractor_specialist.py'.
class DataExtractorSpecialist(BaseSpecialist):
    """
    A functional specialist that extracts structured data from unstructured text.
    It receives text and outputs a predictable JSON object.
    """

    def __init__(self, llm_provider: str):
        # Principle #1 In Action: Loading the prompt from an external file.
        system_prompt = load_prompt("data_extractor_specialist")
        
        super().__init__(system_prompt=system_prompt, llm_provider=llm_provider)
        print("---INITIALIZED DATA EXTRACTOR SPECIALIST (JSON Mode)---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Receives unstructured text from the state and updates the state with
        structured, extracted data.
        """
        print("---EXECUTING DATA EXTRACTOR SPECIALIST---")
        
        unstructured_text = state.get("text_to_process")
        if not unstructured_text:
            raise ValueError("Input text not found in state['text_to_process']")

        messages_to_send = [
            SystemMessage(content=self.system_prompt_content),
            HumanMessage(content=unstructured_text)
        ]

        ai_response_str = self.llm_client.invoke(messages_to_send).content

        try:
            extracted_data = json.loads(ai_response_str)
            if "name" not in extracted_data or "email" not in extracted_data:
                raise ValueError("LLM response did not conform to the required schema.")
            print(f"---SUCCESSFULLY EXTRACTED DATA: {extracted_data}---")
        except (json.JSONDecodeError, ValueError) as e:
            print(f"---ERROR: Failed to parse or validate LLM response. Error: {e}---")
            return {"extracted_data": None, "error": str(e)}

        return {"extracted_data": extracted_data}
