# app/src/specialists/web_builder.py

import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import WebContent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class WebBuilder(BaseSpecialist):
    """
    A specialist that generates or refines a self-contained HTML document based
    on a system_plan or a critique.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        # The specialist's logic is now stateless. It simply acts on the current
        # message history. If a critique was added by the CriticSpecialist, it will
        # be in the history, naturally guiding the LLM to refine the HTML.
        logger.info("Executing WebBuilder logic to generate/refine HTML.")

        # Check for uploaded image (e.g. for "build from mockup")
        image_data = state.get("artifacts", {}).get("uploaded_image.png")

        request = StandardizedLLMRequest(
            messages=state["messages"],
            output_model_class=WebContent,
            image_data=image_data
        )

        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")
        if not json_response:
            raise ValueError("WebBuilder failed to get a valid JSON response from the LLM.")

        web_content = WebContent(**json_response)

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content="Completed HTML generation/refinement. The document is now ready for critique.",
        )
        
        # MODIFICATION: The specialist no longer signals 'task_is_complete'.
        # It simply builds the artifact and recommends the critic. The critic's
        # 'ACCEPT' decision is the new signal for task completion.
        updated_state = {
            "messages": [ai_message],
            "artifacts": {
                "html_document.html": web_content.html_document
            },
            "scratchpad": {"recommended_specialists": ["critic_specialist"]},  # Task 2.7: moved to scratchpad
            # NOTE: routing_history is tracked centrally by GraphOrchestrator.safe_executor
        }

        return updated_state
