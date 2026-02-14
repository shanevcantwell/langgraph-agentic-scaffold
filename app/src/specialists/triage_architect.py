import logging
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import ValidationError
from .base import BaseSpecialist
from ..interface.context_schema import ContextPlan
from ..llm.adapter import StandardizedLLMRequest
from ..utils.errors import SpecialistError

logger = logging.getLogger(__name__)

class TriageArchitect(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # LLM adapter is injected by GraphBuilder via _attach_llm_adapter

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise SpecialistError(f"LLM Adapter not attached to {self.specialist_name}")

        # 1. Get enriched messages (includes gathered_context if available)
        messages = self._get_enriched_messages(state)

        if not messages:
            logger.warning("TriageArchitect received no messages.")
            return {}

        # Check for uploaded content (Blind Triage Support)
        from langchain_core.messages import HumanMessage as HM

        # Handle uploaded text (Data Injection)
        if state.get("artifacts", {}).get("text_to_process"):
            if messages and isinstance(messages[-1], HM):
                last_content = messages[-1].content
                text_length = len(state["artifacts"]["text_to_process"])
                messages = messages[:-1] + [
                    HM(content=last_content + f"\n\n[SYSTEM NOTE: The user has uploaded a document ({text_length} characters). This document is ALREADY AVAILABLE in artifacts - you do NOT need to gather it. Do NOT emit READ_FILE or RESEARCH actions to obtain this document. Emit an empty actions list and recommend an appropriate specialist to process it.]")
                ]

        # Handle uploaded image
        if state.get("artifacts", {}).get("uploaded_image.png"):
            # Append image notification to last message
            if messages and isinstance(messages[-1], HM):
                last_content = messages[-1].content
                messages = messages[:-1] + [
                    HM(content=last_content + "\n\n[SYSTEM NOTE: The user has uploaded an image. You cannot see it, but it is available in the artifacts. Do not ask for the image.]")
                ]

        # 2. Create Request - use adapter's system prompt (configured by GraphBuilder with dynamic specialist roster)
        # NOTE: Do NOT reload prompt file here - GraphBuilder._configure_triage() already assembled
        # the dynamic prompt with specialist descriptions and set it on the adapter.
        request = StandardizedLLMRequest(
            messages=messages,  # No SystemMessage - adapter handles system prompt
            tools=[ContextPlan],
            force_tool_call=True
        )
        
        # 4. Invoke LLM
        try:
            response_data = self.llm_adapter.invoke(request)
            tool_calls = response_data.get("tool_calls", [])

            if not tool_calls:
                logger.warning("TriageArchitect LLM did not return a tool call.")
                return self._fallback_plan("LLM did not return a tool call")

            # Extract the first tool call (ContextPlan)
            plan_args = tool_calls[0].get('args', {})

            # Guard malformed fields before Pydantic validation (#154)
            if not isinstance(plan_args.get("actions"), list):
                plan_args["actions"] = []
            if not plan_args.get("reasoning"):
                plan_args["reasoning"] = "Context plan generated (reasoning was empty)"

            try:
                context_plan = ContextPlan(**plan_args)
            except ValidationError as ve:
                logger.warning(f"TriageArchitect: ContextPlan validation failed: {ve}")
                # Salvage what we can — keep recommended_specialists if present
                context_plan = ContextPlan(
                    reasoning=plan_args.get("reasoning", "Validation fallback"),
                    recommended_specialists=plan_args.get("recommended_specialists", [])
                )

            logger.info(f"TriageArchitect generated plan with {len(context_plan.actions)} actions.")

            # 5. Return triage output to scratchpad (no artifact)
            return {
                "scratchpad": {
                    "triage_reasoning": context_plan.reasoning,
                    "triage_actions": [a.model_dump() for a in context_plan.actions],
                }
            }

        except Exception as e:
            logger.error(f"Error in TriageArchitect: {e}", exc_info=True)
            return self._fallback_plan(str(e))

    def _fallback_plan(self, reason: str) -> Dict[str, Any]:
        """Return a minimal valid ContextPlan when LLM output is unusable (#154)."""
        fallback = ContextPlan(reasoning=f"Triage fallback: {reason}")
        return {
            "messages": [AIMessage(content=f"[Triage] {reason}")],
            "scratchpad": {
                "triage_reasoning": fallback.reasoning,
                "triage_actions": [],
            }
        }
