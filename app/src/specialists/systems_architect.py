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
        # Issue #171: SA is the entry point — produces task_plan (system's theory of user intent)
        # Guard: if task_plan already exists, pass through (e.g., on retry the plan persists)
        existing_plan = state.get("artifacts", {}).get("task_plan")
        if existing_plan:
            logger.info("SystemsArchitect: task_plan already exists, passing through")
            return {
                "messages": [create_llm_message(
                    specialist_name=self.specialist_name,
                    llm_adapter=self.llm_adapter,
                    content=f"Task plan exists: {existing_plan.get('plan_summary', 'see artifacts')}",
                )],
            }

        # Get enriched messages (includes gathered_context if available)
        messages: List[BaseMessage] = self._get_enriched_messages(state)
        plan = self._generate_plan(messages)

        new_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=f"I have created a task plan: {plan.plan_summary}",
        )

        # Task plan is a durable artifact — persists across retries
        # Consumed by Triage (classification), Router (routing), specialists (execution), EI (verification)
        return {
            "messages": [new_message],
            "artifacts": {"task_plan": plan.model_dump()},
        }

    # --- MCP Tool Interface (Issue #115) ---

    def register_mcp_services(self, registry: 'McpRegistry'):
        """Expose planning as MCP service."""
        registry.register_service(self.specialist_name, {
            "create_plan": self.create_plan,
        })
        logger.info(f"SystemsArchitect: Registered MCP service with create_plan method")

    def create_plan(self, context: str, artifact_key: str, available_tools: list = None) -> dict:
        """
        MCP-callable planning service.

        Args:
            context: What to plan for (user request, gathered context)
            artifact_key: Artifact slot to write the plan to
            available_tools: Optional list of {"name", "description"} dicts describing
                the caller's tool capabilities. When provided, execution_steps are
                constrained to only use these tools.

        Returns:
            Update dict with artifacts[artifact_key] = plan
        """
        logger.info(f"SystemsArchitect.create_plan called: artifact_key={artifact_key}")

        if available_tools:
            tool_lines = "\n".join(
                f"- **{t['name']}**: {t['description']}" for t in available_tools
            )
            context += (
                f"\n\nThe executor has ONLY these tools:\n{tool_lines}\n\n"
                "All execution_steps MUST be achievable using only these tools. "
                "Do not assume shell commands, checksums, hashing, or other capabilities."
            )

        messages = [HumanMessage(content=context)]
        plan = self._generate_plan(messages)
        logger.info(f"SystemsArchitect.create_plan produced: {plan.plan_summary}")
        return {"artifacts": {artifact_key: plan.model_dump()}}
