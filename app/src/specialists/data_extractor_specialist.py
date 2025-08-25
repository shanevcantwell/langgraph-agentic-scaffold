# app/src/specialists/data_extractor_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_missing_artifact_response, create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import ExtractedData

logger = logging.getLogger(__name__)

class DataExtractorSpecialist(BaseSpecialist):
    """
    A specialist that extracts structured data from a given text using an LLM.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"][:]
        text_to_process = state.get("text_to_process")

        if not text_to_process:
            return create_missing_artifact_response(
                specialist_name=self.specialist_name,
                required_artifact="text_to_process",
                recommended_specialist="file_specialist"
            )
            
        # The specialist's system prompt (loaded at init) should already instruct it
        # to extract data from text provided in the user message. We will construct a new
        # message list that includes the text to be processed as a new user turn.
        contextual_messages = messages + [HumanMessage(content=f"Please extract the requested data from the following text:\n\n---\n{text_to_process}\n---")]

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

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have successfully extracted the following data: {extracted_data}",
        )

        # The task is only complete if this specialist was not part of a larger plan.
        # The presence of a 'system_plan' artifact is the key indicator.
        is_part_of_larger_plan = state.get("system_plan") is not None
        task_is_complete = not is_part_of_larger_plan

        return {
            "messages": [ai_message],
            "extracted_data": extracted_data,
            "task_is_complete": task_is_complete
        }