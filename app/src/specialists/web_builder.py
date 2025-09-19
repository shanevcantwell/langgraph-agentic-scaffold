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
        # MODIFICATION: Remove all logic related to 'refinement_cycles' and 'iteration'.
        # The specialist's job is to build or revise, not to manage loops.
        
        critique = state.get("artifacts", {}).get("critique.md")
        current_html = state.get("artifacts", {}).get("html_document.html")
        
        logger.info("Executing WebBuilder logic.")

        contextual_messages: List[BaseMessage] = state["messages"][:]

        # If we have existing HTML and a critique, this is a refinement cycle.
        if current_html and critique:
            logger.info("Refining existing HTML based on critique.")
            refinement_prompt = HumanMessage(content=(
                "This is a refinement cycle. Please improve the following HTML based on the critique provided in the conversation history.\n\n"
                f"Here is the previous HTML to improve:\n```html\n{current_html}\n```\n\n"
                f"And here is the critique to address:\n```\n{critique}\n```"
            ))
            contextual_messages.append(refinement_prompt)
        else:
            logger.info("Performing initial HTML build from system plan.")

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=WebContent
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
            "recommended_specialists": ["critic_specialist"]
        }

        return updated_state
