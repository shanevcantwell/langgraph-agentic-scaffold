# app/src/specialists/data_extractor_specialist.py
import logging
from typing import Dict, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import ExtractedData

logger = logging.getLogger(__name__)

class DataExtractorSpecialist(BaseSpecialist):
    """
    A specialist that extracts structured data from a given text using an LLM.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages = state.get("messages", [])
        text_to_process = state.get("artifacts", {}).get("text_to_process")

        # Fallback: if no artifact, use the last human message content directly
        if not text_to_process or not text_to_process.strip():
            last_human_msg = next(
                (m for m in reversed(messages) if isinstance(m, HumanMessage)),
                None
            )
            if last_human_msg and last_human_msg.content.strip():
                text_to_process = last_human_msg.content
                logger.info("DataExtractorSpecialist: No 'text_to_process' artifact, using message content directly.")

        if not text_to_process or not text_to_process.strip():
            logger.warning("DataExtractorSpecialist cannot execute: no text available (artifact or message).")
            ai_message = create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content="I cannot extract data because no text was provided."
            )
            return {"messages": [ai_message]}

        contextual_messages = messages + [HumanMessage(content=f"Please extract the requested data from the following text:\n\n---\n{text_to_process}\n---")]

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=ExtractedData
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response or "extracted_json" not in json_response:
            raise ValueError("DataExtractorSpecialist failed to get a valid JSON response from the LLM.")

        extracted_data = ExtractedData(**json_response).extracted_json
        logger.info(f"Successfully extracted data: {extracted_data}")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have successfully extracted the following data: {extracted_data}",
        )

        return {
            "messages": [ai_message],
            "artifacts": {"extracted_data": extracted_data},
            "task_is_complete": True,
        }