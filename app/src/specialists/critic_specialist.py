# app/src/specialists/critic_specialist.py
import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
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
            error_message = "Critic Error: 'html_artifact' not found in state. Cannot provide a critique."
            logger.warning(error_message)
            return {
                "messages": [AIMessage(content=error_message, name=self.specialist_name)],
                "recommended_specialists": ["web_builder"]
            }

        messages: List[BaseMessage] = state["messages"]
        contextual_messages = messages[:]

        contextual_messages.append(HumanMessage(
            content=f"Here is the HTML document to critique:\n\n```html\n{html_artifact}\n```"
        ))

        request = StandardizedLLMRequest(messages=contextual_messages)
        response_data = self.llm_adapter.invoke(request)
        critique = response_data.get("text_response", "No critique provided.")

        logger.info("Critique generated. Recommending SystemsArchitect for plan revision.")

        return {
            "messages": [AIMessage(content=f"Critique complete. The next step is to revise the plan.", name=self.specialist_name)],
            "critique_artifact": critique,
            "recommended_specialists": ["systems_architect"]
        }