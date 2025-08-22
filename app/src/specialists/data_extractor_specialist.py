# app/src/specialists/data_extractor_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from pydantic import BaseModel

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class ExtractedData(BaseModel):
    """A Pydantic model to guide the LLM's JSON output."""
    extracted_json: Dict[str, Any]

class DataExtractorSpecialist(BaseSpecialist):
    """
    A specialist that extracts structured data from a given text using an LLM.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"][:]
        text_to_process = state.get("text_to_process")

        if not text_to_process:
            logger.warning("DataExtractorSpecialist was called without text to process. Adding a message to the state and returning control to the router.")
            # This is a more prescriptive "self-correction" message. It gives the router's LLM
            # a strong hint about what to do next, helping to break reasoning loops.
            ai_message = AIMessage(
                content="I am the Data Extractor. I cannot run because there is no text to process. The user's request seems to involve a file. The 'file_specialist' should probably run first to read the file content into the state."
            )
            return {
                "messages": [ai_message],
                "extracted_data": None,
                "text_to_process": None
            }

        contextual_messages = messages + [SystemMessage(content=f"Here is the text to analyze:\n\n---\n{text_to_process}\n---")]

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=ExtractedData
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response or "extracted_json" not in json_response:
            raise ValueError("DataExtractorSpecialist failed to get a valid JSON response from the LLM.")

        extracted_data = json_response["extracted_json"]
        logger.info(f"Successfully extracted data: {extracted_data}")

        ai_message = AIMessage(content=f"I have successfully extracted the following data: {extracted_data}")

        return {
            "messages": [ai_message],
            "extracted_data": extracted_data,
            "text_to_process": None,
            "task_is_complete": True # Signal that a terminal analysis has been performed.
        }