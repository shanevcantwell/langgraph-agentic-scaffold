# src/specialists/data_extractor_specialist.py

import json
from typing import Dict, Any, Optional

from pydantic import BaseModel, ValidationError

# Principle #1 In Action: Importing the prompt loader
from ..utils.prompt_loader import PromptLoader
from .base import BaseSpecialist
from ..graph.state import GraphState
from langchain_core.messages import SystemMessage, HumanMessage

class ExtractedData(BaseModel):
    """Defines the expected schema for the extracted data using Pydantic."""
    name: Optional[str] = None
    email: Optional[str] = None

# Principle #2 In Action: The class name 'DataExtractorSpecialist' matches
# the filename 'data_extractor_specialist.py'.
class DataExtractorSpecialist(BaseSpecialist):
    """
    A functional specialist that extracts structured data from unstructured text.
    It receives text and outputs a predictable JSON object.
    """

    def __init__(self, llm_provider: str):
        # Principle #1 In Action: Loading the prompt from an external file.
        system_prompt = PromptLoader.load("data_extractor_specialist")
        
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
            # 1. First, parse the raw JSON string from the LLM
            raw_data = json.loads(ai_response_str)
            # 2. Then, validate the data against our Pydantic schema
            validated_data = ExtractedData.model_validate(raw_data)
            print(f"---SUCCESSFULLY EXTRACTED & VALIDATED DATA: {validated_data.model_dump_json()}---")
            # 3. Return the validated data as a dictionary for the graph state
            return {"extracted_data": validated_data.model_dump()}
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"---ERROR: Failed to parse or validate LLM response. Error: {e}---")
            # It's good practice to return the raw response for easier debugging
            return {
                "extracted_data": None, 
                "error": str(e),
                "raw_response": ai_response_str
            }
