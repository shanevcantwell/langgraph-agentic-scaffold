# app/src/specialists/critic_specialist.py
import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_missing_artifact_response, create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

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

        request = StandardizedLLMRequest(messages=contextual_messages)
        response_data = self.llm_adapter.invoke(request)
        critique = response_data.get("text_response", "No critique provided.")

        logger.info("Critique generated. Recommending SystemsArchitect for plan revision.")

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"Critique complete. The next step is to revise the plan.",
        )
        return {
            "messages": [ai_message],
            "critique_artifact": critique,
            "recommended_specialists": ["systems_architect"]
        }