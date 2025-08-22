# app/src/specialists/text_analysis_specialist.py

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, HumanMessage

class TextAnalysisSpecialist(BaseSpecialist):
    """
    A specialist that analyzes or summarizes a block of text provided in the state.
    It expects the text to be present in the `text_to_process` key.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)

    def _execute_logic(self, state: dict) -> dict:
        """
        Analyzes text from the state and adds the result to the messages.
        """
        text_to_process = state.get("text_to_process")

        if not text_to_process:
            error_message = "TextAnalysisSpecialist was called, but no text was found in the state's 'text_to_process' key."
            return {"messages": state["messages"] + [AIMessage(content=error_message)]}

        # Append the text to be analyzed to the message history for full context.
        messages_for_llm = state["messages"] + [
            HumanMessage(
                content=(
                    "--- TEXT TO ANALYZE ---\n"
                    "Based on our conversation, please perform the requested analysis on the text above.\n\n"
                    f"{text_to_process}"
                )
            )
        ]

        request = StandardizedLLMRequest(
            messages=messages_for_llm
        )

        response_data = self.llm_adapter.invoke(request)
        ai_response_content = response_data.get("text_response", "I was unable to analyze the text.")
        ai_message = AIMessage(content=ai_response_content)

        # Consume the artifact and return the final analysis as the new message.
        return {
            "messages": state["messages"] + [ai_message],
            "text_to_process": None
        }