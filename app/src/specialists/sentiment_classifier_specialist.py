# app/src/specialists/sentiment_classifier_specialist.py

from .base import BaseSpecialist
from .helpers import create_error_message, create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, BaseMessage
from typing import Dict, Any, List, Literal
from pydantic import ValidationError, BaseModel, Field

class Sentiment(BaseModel):
    """A Pydantic model for classifying sentiment."""
    sentiment: Literal["positive", "negative", "neutral"] = Field(..., description="The sentiment of the text.")


class SentimentClassifierSpecialist(BaseSpecialist):
    """A specialist that classifies the sentiment of a user's message."""

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        """Initializes the specialist."""
        super().__init__(specialist_name, specialist_config)

    def _execute_logic(self, state: dict) -> dict:
        """Classifies the sentiment of the user's message."""
        # Find the last human message to analyze
        last_human_message = next(
            (msg for msg in reversed(state.get("messages", [])) if isinstance(msg, BaseMessage) and msg.type == "human"),
            None,
        )

        if not last_human_message:
            return create_error_message(
                "I cannot run because there is no text to analyze.",
                recommended_specialists=["default_responder_specialist"],
            )

        request = StandardizedLLMRequest(
            messages=[last_human_message],
            output_model_class=Sentiment
        )

        try:
            response_data = self.llm_adapter.invoke(request)
            json_response = response_data.get("json_response")
            if not json_response:
                return create_error_message(
                    "I was unable to parse the sentiment from the LLM's response because the LLM did not return a 'json_response'."
                )

            # Let Pydantic validation run.
            classification = Sentiment(**json_response)
            ai_message = create_llm_message(
                specialist_name=self.specialist_name,
                llm_adapter=self.llm_adapter,
                content=f"The sentiment of the message is: {classification.sentiment}",
            )
            # Return only the new message and artifact. The graph will append them to the state.
            return {"messages": [ai_message], "artifacts": {"json_artifact": classification.model_dump()}}

        except ValidationError as e:
            error_detail = f"Pydantic validation failed: {e}"
            return create_error_message(
                f"I was unable to parse the sentiment from the LLM's response. Details: {error_detail}"
            )
        except Exception as e:
            # Catch any other unexpected errors during processing
            return create_error_message(
                f"An unexpected error occurred while classifying sentiment: {e}"
            )
