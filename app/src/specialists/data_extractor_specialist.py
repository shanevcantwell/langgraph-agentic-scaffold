# src/specialists/data_extractor_specialist.py

import logging
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas import ExtractedData
from langchain_core.messages import HumanMessage, AIMessage
from typing import Dict, Any

logger = logging.getLogger(__name__)

class DataExtractorSpecialist(BaseSpecialist):
    """
    A functional specialist that extracts structured data from unstructured text.
    It receives text and outputs a predictable JSON object using schema enforcement.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Receives unstructured text from the state and updates the state with
        structured, extracted data.
        """
        text_to_process = state.get("text_to_process")
        if not text_to_process:
            raise ValueError("Input text not found in state['text_to_process']")

        # Append the text to be processed to the message history so the LLM has full context
        # of the user's request. This is more robust than creating a new, isolated prompt.
        messages_for_llm = state["messages"] + [
            HumanMessage(
                content=(
                    "--- TEXT TO PROCESS ---\n"
                    "Based on our conversation, please extract the relevant information from the text above "
                    "into the required JSON format.\n\n"
                    f"{text_to_process}"
                )
            )
        ]

        request = StandardizedLLMRequest(
            messages=messages_for_llm,
            output_model_class=ExtractedData
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("DataExtractor failed to get a valid JSON response from the LLM.")

        validated_data = ExtractedData(**json_response)
        new_message = AIMessage(content="I have successfully extracted the structured data.")
        return {
            "messages": state["messages"] + [new_message],
            "json_artifact": validated_data.extracted_json,
            "text_to_process": None  # Consume the artifact after processing
        }
