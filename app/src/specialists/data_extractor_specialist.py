# src/specialists/data_extractor_specialist.py

import logging
import json
from typing import Dict, Any, Optional

from pydantic import BaseModel, ValidationError

# Principle #1 In Action: Importing the prompt loader
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..graph.state import GraphState
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

class ExtractedData(BaseModel):
    """Defines the expected schema for the extracted data using Pydantic."""
    extracted_json: Optional[Dict[str, Any]] = None

# Principle #2 In Action: The class name 'DataExtractorSpecialist' matches
# the filename 'data_extractor_specialist.py'.
class DataExtractorSpecialist(BaseSpecialist):
    """
    A functional specialist that extracts structured data from unstructured text.
    It receives text and outputs a predictable JSON object.
    """

    def __init__(self):
        super().__init__(specialist_name="data_extractor_specialist")
        logger.info(f"---INITIALIZED {self.__class__.__name__}---")

    def execute(self, state: GraphState) -> Dict[str, Any]:
        """
        Receives unstructured text from the state and updates the state with
        structured, extracted data.
        """
        logger.info("---EXECUTING DATA EXTRACTOR SPECIALIST---")
        
        unstructured_text = state.get("text_to_process")
        if not unstructured_text:
            raise ValueError("Input text not found in state['text_to_process']")

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=unstructured_text)],
            # The system prompt is now managed by the adapter
        )

        # Use the adapter, not a direct client
        ai_response_str = self.llm_adapter.invoke(request)
        
        extracted_json_str = ai_response_str.strip()
        # Models often wrap JSON in markdown code fences. Let's strip them.
        if extracted_json_str.startswith("```json"):
            extracted_json_str = extracted_json_str[len("```json"):]
        if extracted_json_str.startswith("```"):
            extracted_json_str = extracted_json_str[len("```"):]
        if extracted_json_str.endswith("```"):
            extracted_json_str = extracted_json_str[:-len("```")]

        # After stripping fences, we should have a clean JSON string.
        extracted_json_str = extracted_json_str.strip()

        try:
            # 1. First, parse the raw JSON string from the LLM
            raw_data = json.loads(extracted_json_str)
            # 2. Then, validate the data against our Pydantic schema
            validated_data = ExtractedData.model_validate(raw_data)
            logger.info(f"---SUCCESSFULLY EXTRACTED & VALIDATED DATA: {validated_data.model_dump_json()}---")
            # 3. Return the validated data as a dictionary for the graph state
            # The graph is wired to return to the router. Do not hardcode the next specialist.
            return {"json_artifact": validated_data.extracted_json, "error": None}
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"---ERROR: Failed to parse or validate LLM response. Error: {e}---")
            logger.debug(f"---RAW LLM RESPONSE: {ai_response_str}---")
            logger.debug(f"---ATTEMPTED JSON PARSE STRING: {extracted_json_str}---")
            # It's good practice to return the raw response for easier debugging
            return {
                "json_artifact": None, 
                "error": str(e),
                "raw_response": ai_response_str
            }
