# app/src/specialists/text_analysis_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_missing_artifact_response, create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import AnalysisResult

logger = logging.getLogger(__name__)

class TextAnalysisSpecialist(BaseSpecialist):
    """
    A specialist that performs analysis on a given text, such as summarizing
    or extracting key points.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        text_to_process = state.get("text_to_process")

        if not text_to_process:
            return create_missing_artifact_response(
                specialist_name=self.specialist_name,
                required_artifact="text_to_process",
                recommended_specialist="file_specialist"
            )
            return {
                "messages": [ai_message],
                "recommended_specialists": ["file_specialist"]
            }

        # The specialist's system prompt (loaded at init) should already instruct it
        # to analyze text provided in the user message. We will construct a new
        # message list that includes the text to be processed as a new user turn.
        contextual_messages = messages + [HumanMessage(content=f"Please perform the requested analysis on the following text:\n\n---\n{text_to_process}\n---")]

        request = StandardizedLLMRequest(
            messages=contextual_messages, output_model_class=AnalysisResult
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("TextAnalysisSpecialist failed to get a valid JSON response from the LLM.")

        report = f"I have analyzed the text as requested.\n\n**Summary:**\n{json_response.get('summary', 'N/A')}\n\n**Main Points:**\n"
        for point in json_response.get("main_points", []):
            report += f"- {point}\n"

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=report,
        )
        return {
            "messages": [ai_message],
            "json_artifact": json_response,
            # This specialist should NOT decide if the task is complete.
            # It provides its analysis and returns control to the router.
        }