# app/src/specialists/sentiment_classifier_specialist.py

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import Sentiment
from langchain_core.messages import AIMessage, BaseMessage
from typing import Dict, Any, List

class SentimentClassifierSpecialist(BaseSpecialist):
    """A specialist that classifies the sentiment of a user's message."""

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """Initializes the specialist."""
        super().__init__(specialist_name, specialist_config)

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
        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"The sentiment of the message is: {classification.sentiment}",
        )

        # Return only the new message and artifact. The graph will append them to the state.
        # This follows the "atomic state updates" pattern.
        return {"messages": [ai_message], "json_artifact": classification.model_dump()}
