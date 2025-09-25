# app/src/specialists/text_analysis_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import TextAnalysis

logger = logging.getLogger(__name__)

class TextAnalysisSpecialist(BaseSpecialist):
    """
    A specialist that performs analysis on a given text, such as summarizing
    or extracting key points.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        text_to_process = state.get("artifacts", {}).get("text_to_process")

        if not text_to_process or not text_to_process.strip():
            logger.warning("TextAnalysisSpecialist cannot run because 'text_to_process' artifact is missing or empty.")
            ai_message = create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content="I cannot run because there is no text to process. The 'file_specialist' should probably run first to load a file into context."
            )
            # Recommend a specialist that can provide the missing artifact
            return {"messages": [ai_message], "recommended_specialists": ["file_specialist"]}

        contextual_messages = messages + [HumanMessage(content=f"Please perform the requested analysis on the following text:\n\n---\n{text_to_process}\n---")]

        request = StandardizedLLMRequest(
            messages=contextual_messages, output_model_class=TextAnalysis
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("TextAnalysisSpecialist failed to get a valid JSON response from the LLM.")

        # Build the human-readable report from the structured JSON response
        report = f"I have analyzed the text as requested.\n\n**Summary:**\n{json_response.get('summary', 'N/A')}\n\n**Main Points:**\n"
        main_points = json_response.get("main_points", [])
        for point in main_points:
            report += f"- {point}\n"

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=report,
        )

        updated_state = {
            "messages": [ai_message],
            "artifacts": {
                "text_analysis_report.md": report,
                "text_analysis": json_response # Store the structured data as well
            },
        }

        return updated_state