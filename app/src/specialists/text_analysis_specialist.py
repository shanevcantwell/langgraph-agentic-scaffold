# app/src/specialists/text_analysis_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from pydantic import BaseModel

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class AnalysisResult(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for text analysis."""
    summary: str
    main_points: List[str]

class TextAnalysisSpecialist(BaseSpecialist):
    """
    A specialist that performs analysis on a given text, such as summarizing
    or extracting key points.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        text_to_process = state.get("text_to_process")

        if not text_to_process:
            logger.warning("TextAnalysisSpecialist was called without text to process. Adding a message to the state and returning control to the router.")
            # This is a prescriptive "self-correction" message. It gives the router's LLM
            # a strong hint about what to do next, helping to break reasoning loops.
            ai_message = AIMessage(
                content="I am the Text Analysis specialist. I cannot run because there is no text to process. The user's request seems to involve a file. The 'file_specialist' should probably run first to read the file content into the state."
            )
            return {"messages": [ai_message], "text_to_process": None}

        last_human_message = next((m.content for m in reversed(messages) if m.type == 'human'), "Analyze the following text.")
        
        system_prompt = (
            f"You are a text analysis expert. Your task is to carefully analyze the provided text based on the user's request. "
            f"The user's request was: '{last_human_message}'. "
            f"Respond with a JSON object containing the analysis."
        )

        contextual_messages = [
            SystemMessage(content=system_prompt),
            SystemMessage(content=f"Here is the text to analyze:\n\n---\n{text_to_process}\n---")
        ]

        request = StandardizedLLMRequest(messages=contextual_messages, output_model_class=AnalysisResult)
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("TextAnalysisSpecialist failed to get a valid JSON response from the LLM.")

        report = f"I have analyzed the text as requested.\n\n**Summary:**\n{json_response.get('summary', 'N/A')}\n\n**Main Points:**\n"
        for point in json_response.get("main_points", []):
            report += f"- {point}\n"

        return {
            "messages": [AIMessage(content=report)],
            "text_to_process": None,
            "task_is_complete": True # Signal that a terminal analysis has been performed.
        }