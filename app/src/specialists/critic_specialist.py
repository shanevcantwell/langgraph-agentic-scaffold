# app/src/specialists/critic_specialist.py
import logging
from typing import Dict, Any, List

import jmespath
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import Critique
from langchain_core.messages import BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class CriticSpecialist(BaseSpecialist):
    """
    A specialist that analyzes an HTML artifact and provides a critique for
    improvement. It is a key part of the refinement loop.
    """

    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        logger.info("---INITIALIZED CriticSpecialist---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        logger.info("Executing CriticSpecialist logic.")
        html_artifact = state.get("html_artifact")

        messages: List[BaseMessage] = state["messages"]
        contextual_messages = messages[:]

        contextual_messages.append(HumanMessage(
            content=f"Here is the HTML document to critique:\n\n```html\n{html_artifact}\n```"
        ))

        # Use the new schema for structured output
        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=Critique
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            # Fallback for when the LLM fails to produce structured output
            logger.warning("Critic LLM failed to return a valid structured response. Falling back to text.")
            critique_text = response_data.get("text_response", "The critic LLM failed to provide a response.")
        else:
            # Use JMESPath to robustly extract data, regardless of nesting.
            # Check for keys at the top level, or nested one level under a 'critique' key.
            assessment_str = jmespath.search('overall_assessment || assessment || critique.overall_assessment || critique.assessment', json_response)
            improvements_list = jmespath.search('points_for_improvement || improvements || critique.points_for_improvement || critique.improvements', json_response) or []
            positives_list = jmespath.search('positive_feedback || critique.positive_feedback', json_response) or []

            final_assessment = str(assessment_str) if assessment_str else "No assessment provided."
            
            final_improvements = []
            if isinstance(improvements_list, list):
                for item in improvements_list:
                    if isinstance(item, dict):
                        # If the item is a dict, join its values into a string.
                        final_improvements.append(": ".join(str(v) for v in item.values()))
                    elif isinstance(item, str):
                        final_improvements.append(item)

            final_positives = []
            if isinstance(positives_list, list):
                for item in positives_list:
                    if isinstance(item, dict):
                        final_positives.append(": ".join(str(v) for v in item.values()))
                    elif isinstance(item, str):
                        final_positives.append(item)

            critique_data = {
                "overall_assessment": final_assessment,
                "points_for_improvement": final_improvements,
                "positive_feedback": final_positives,
            }

            try:
                # Format the structured critique into a readable markdown string for the artifact
                critique = Critique(**critique_data)
            except Exception as e:
                logger.error(f"Pydantic validation failed for critic even after JMESPath extraction: {e}", exc_info=True)
                raise e # Re-raise to be caught by the base specialist's error handler

            critique_text_parts = [f"**Overall Assessment:**\n{critique.overall_assessment}\n"]
            if critique.points_for_improvement:
                improvement_points = "\n".join([f"- {point}" for point in critique.points_for_improvement])
                critique_text_parts.append(f"**Points for Improvement:**\n{improvement_points}\n")
            if critique.positive_feedback:
                positive_points = "\n".join([f"- {point}" for point in critique.positive_feedback])
                critique_text_parts.append(f"**What Went Well:**\n{positive_points}")
            critique_text = "\n".join(critique_text_parts)

        logger.info("Critique generated. Recommending WebBuilder for refinement.")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"Critique complete. Returning to the Web Builder for refinement.",
        )
        return {
            "messages": [ai_message],
            "critique_artifact": critique_text,
            "recommended_specialists": ["web_builder"]
        }