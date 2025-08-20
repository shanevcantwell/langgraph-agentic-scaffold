# app/src/specialists/sentiment_classifier_specialist.py

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas import Sentiment
from langchain_core.messages import AIMessage, BaseMessage
from typing import Dict, Any, List

class SentimentClassifierSpecialist(BaseSpecialist):
    """A specialist that classifies the sentiment of a user's message."""

    def __init__(self):
        """Initializes the specialist."""
        super().__init__(specialist_name="sentiment_classifier_specialist")

    def _execute_logic(self, state: dict) -> dict:
        """Classifies the sentiment of the user's message."""
        messages: List[BaseMessage] = state.get("messages", [])
        if not messages:
            raise ValueError("Cannot classify sentiment of empty message history.")

        request = StandardizedLLMRequest(
            messages=messages,
            output_model_class=Sentiment
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("SentimentClassifier failed to get a valid JSON response from the LLM.")

        classification = Sentiment(**json_response)
        ai_message = AIMessage(content=f"The sentiment of the message is: {classification.sentiment}")

        # Return the updated messages and the structured sentiment as a new artifact
        return {"messages": state["messages"] + [ai_message], "sentiment": classification.sentiment}
