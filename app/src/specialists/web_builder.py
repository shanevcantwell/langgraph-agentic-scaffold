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
    on a system_plan. Standard hub-and-spoke specialist — completion is evaluated
    by Exit Interview via classify_interrupt.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        logger.info(f"---INITIALIZED {self.specialist_name}---")

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        logger.info("Executing WebBuilder logic to generate HTML.")

        artifacts = state.get("artifacts", {})

        # Check for uploaded image (e.g. for "build from mockup")
        image_data = artifacts.get("uploaded_image.png")

        # SA MCP Integration: Get or create system_plan
        system_plan = artifacts.get("system_plan")
        created_plan = False  # Track if we created a new plan
        if not system_plan and hasattr(self, 'mcp_client') and self.mcp_client:
            # No plan exists - call SA via MCP to create one
            user_request = artifacts.get("user_request", "Build a web UI")
            logger.info("WebBuilder: No system_plan found, calling SA via MCP")
            try:
                plan_result = self.mcp_client.call(
                    "systems_architect",
                    "create_plan",
                    context=user_request,
                    artifact_key="system_plan"
                )
                system_plan = plan_result.get("artifacts", {}).get("system_plan")
                if system_plan:
                    created_plan = True
                    logger.info(f"WebBuilder: Got plan from SA: {system_plan.get('plan_summary', 'N/A')}")
            except Exception as e:
                logger.warning(f"WebBuilder: Failed to get plan from SA: {e}")

        # Build messages - inject plan if we have one
        messages = self._get_enriched_messages(state)
        if system_plan:
            plan_text = f"## System Plan\n**Summary:** {system_plan.get('plan_summary', '')}\n\n**Steps:**\n"
            for step in system_plan.get('execution_steps', []):
                plan_text += f"- {step}\n"
            # Prepend plan to messages so LLM sees it first
            messages = [HumanMessage(content=plan_text)] + messages

        request = StandardizedLLMRequest(
            messages=messages,
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
            content="HTML generation complete.",
        )
        
        output_artifacts = {"html_document.html": web_content.html_document}

        # Persist the plan if we created it via MCP
        if created_plan and system_plan:
            output_artifacts["system_plan"] = system_plan

        updated_state = {
            "messages": [ai_message],
            "artifacts": output_artifacts,
            "scratchpad": {},
        }

        return updated_state
