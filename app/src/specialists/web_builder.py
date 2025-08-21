import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from .schemas import WebContent
from langchain_core.messages import AIMessage, BaseMessage

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    """
    A specialist that generates a self-contained HTML document based on a
    system_plan artifact in the state.
    """
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name=specialist_name)
        logger.info("---INITIALIZED WebBuilder---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]
        system_plan = state.get("system_plan")
        if not system_plan:
            raise ValueError("WebBuilder Error: 'system_plan' not found in state.")

        request = StandardizedLLMRequest(
            messages=messages,
            output_model_class=WebContent
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("WebBuilder failed to get a valid HTML document from the LLM.")

        web_content = WebContent(**json_response)

        new_message = AIMessage(content="I have generated the HTML document based on the system plan.")
        updated_state = {
            "messages": state["messages"] + [new_message],
            "html_artifact": web_content.html_document
        }
        return updated_state
