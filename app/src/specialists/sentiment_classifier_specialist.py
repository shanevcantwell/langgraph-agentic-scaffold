# app/src/specialists/sentiment_classifier_specialist.py

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, HumanMessage

class SentimentClassifierSpecialist(BaseSpecialist):
    """A specialist that classifies the sentiment of a user's message."""

    def __init__(self):
        """Initializes the specialist."""
        super().__init__(specialist_name="sentiment_classifier_specialist")

    def execute(self, state: dict) -> dict:
        """Classifies the sentiment of the user's message."""
        user_input = state["messages"][-1].content

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=user_input)],
            output_schema={"sentiment": "(positive|negative|neutral)"}
        )

        response_data = self.llm_adapter.invoke(request)

        sentiment = response_data['json_response']['sentiment']
        ai_message = AIMessage(content=f"The sentiment of the message is: {sentiment}")

        return {"messages": state["messages"] + [ai_message]}
