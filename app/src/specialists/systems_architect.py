# app/src/specialists/systems_architect.py

import logging
from typing import Dict, Any, List

from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from .schemas import SystemPlan
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

logger = logging.getLogger(__name__)

class SystemsArchitect(BaseSpecialist):
    """
    A specialist that analyzes a user request and creates a high-level
    technical plan for implementation, adding it to the state.
    """
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name=specialist_name, specialist_config=specialist_config)
        logger.info("---INITIALIZED SystemsArchitect---")

    def _generate_plan(self, messages: List[BaseMessage]) -> SystemPlan:
        """
        Core planning logic - shared by graph execution and MCP tool.

        Args:
            messages: The messages to send to the LLM

        Returns:
            SystemPlan instance
        """
        request = StandardizedLLMRequest(
            messages=messages,
            output_model_class=SystemPlan
        )

        # Adapter raises ValueError if structured output parsing fails
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("SystemsArchitect failed to get a valid plan from the LLM.")

        return SystemPlan(**json_response)

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        # "Not me" pattern: if system_plan already exists, don't create another
        # Add self to forbidden_specialists so Router won't route back here
        existing_plan = state.get("artifacts", {}).get("system_plan")
        if existing_plan:
            logger.info("SystemsArchitect: system_plan already exists, adding self to forbidden_specialists")
            return {
                "messages": [create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"A system plan already exists: {existing_plan.get('plan_summary', 'see artifacts')}",
                )],
                "scratchpad": {"forbidden_specialists": [self.specialist_name]},
            }

        # Get enriched messages (includes gathered_context if available)
        messages: List[BaseMessage] = self._get_enriched_messages(state)
        plan = self._generate_plan(messages)

        new_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have created a system plan: {plan.plan_summary}",
        )

        # System Plan is a durable output - placed in artifacts
        # Add self to forbidden_specialists: job done, don't route back here
        return {
            "messages": [new_message],
            "artifacts": {"system_plan": plan.model_dump()},
            "scratchpad": {"forbidden_specialists": [self.specialist_name]},
        }

    # --- MCP Tool Interface (Issue #115) ---

    def register_mcp_services(self, registry: 'McpRegistry'):
        """Expose planning as MCP service."""
        registry.register_service(self.specialist_name, {
            "create_plan": self.create_plan,
        })
        logger.info(f"SystemsArchitect: Registered MCP service with create_plan method")

    def create_plan(self, context: str, artifact_key: str) -> dict:
        """
        MCP-callable planning service.

        Args:
            context: What to plan for (user request, gathered context)
            artifact_key: Artifact slot to write the plan to

        Returns:
            Update dict with artifacts[artifact_key] = plan
        """
        logger.info(f"SystemsArchitect.create_plan called: artifact_key={artifact_key}")
        messages = [HumanMessage(content=context)]
        plan = self._generate_plan(messages)
        logger.info(f"SystemsArchitect.create_plan produced: {plan.plan_summary}")
        return {"artifacts": {artifact_key: plan.model_dump()}}
