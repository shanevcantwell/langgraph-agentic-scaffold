# app/src/specialists/critic_specialist.py
import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_missing_artifact_response, create_llm_message
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

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        logger.info("Executing CriticSpecialist logic.")
        html_artifact = state.get("html_artifact")
        if not html_artifact:
            return create_missing_artifact_response(
                specialist_name=self.specialist_name,
                required_artifact="html_artifact",
                recommended_specialist="web_builder"
            )

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
            # --- Response Normalization ---
            # Some models (like Gemini) might nest the response inside a single key
            # (e.g., {"critique": {...}}). If the top-level dict has one key and
            # its value is a dict, we'll assume that's the actual payload.
            critique_data = json_response
            if isinstance(json_response, dict) and len(json_response) == 1:
                key = next(iter(json_response))
                if isinstance(json_response[key], dict):
                    logger.debug(f"Found response nested under key '{key}'. Un-nesting.")
                    critique_data = json_response[key]

            # --- Flattening Logic ---
            # Now, check if the data matches the schema or if it's further nested by category.
            expected_keys = Critique.model_fields.keys()
            if not any(key in critique_data for key in expected_keys):
                logger.debug("Response appears to be nested by category. Attempting to flatten.")
                flattened_data = {
                    "overall_assessment": [],
                    "points_for_improvement": [],
                    "positive_feedback": []
                }
                # Iterate through the categorized dictionary (e.g., {"visual_design": {...}, "code_quality": {...}})
                for category, details in critique_data.items():
                    if isinstance(details, dict):
                        # Look for keys that sound like our target fields.
                        # This is more robust than hardcoding 'assessment', 'improvements', etc.
                        for key, value in details.items():
                            if 'assess' in key.lower() and isinstance(value, str):
                                flattened_data["overall_assessment"].append(value)
                            elif 'improve' in key.lower() and isinstance(value, list):
                                flattened_data["points_for_improvement"].extend(value)
                            elif 'positive' in key.lower() and isinstance(value, list):
                                flattened_data["positive_feedback"].extend(value)
                
                # Join the collected assessments into a single string.
                flattened_data["overall_assessment"] = " ".join(flattened_data["overall_assessment"])
                critique_data = flattened_data

            try:
                # Format the structured critique into a readable markdown string for the artifact
                critique = Critique(**critique_data)
            except Exception as e:
                logger.error(f"Pydantic validation failed for critic even after attempting to flatten the response: {e}")
                raise e # Re-raise to be caught by the base specialist's error handler

            critique_text_parts = [f"**Overall Assessment:**\n{critique.overall_assessment}\n"]
            if critique.points_for_improvement:
                improvement_points = "\n".join([f"- {point}" for point in critique.points_for_improvement])
                critique_text_parts.append(f"**Points for Improvement:**\n{improvement_points}\n")
            if critique.positive_feedback:
                positive_points = "\n".join([f"- {point}" for point in critique.positive_feedback])
                critique_text_parts.append(f"**What Went Well:**\n{positive_points}")
            critique_text = "\n".join(critique_text_parts)

        logger.info("Critique generated. Recommending SystemsArchitect for plan revision.")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"Critique complete. The next step is to revise the plan.",
        )
        return {
            "messages": [ai_message],
            "critique_artifact": critique_text,
            "recommended_specialists": ["systems_architect"]
        }