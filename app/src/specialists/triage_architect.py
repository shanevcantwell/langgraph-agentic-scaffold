import logging
from typing import Dict, Any, List
from langchain_core.messages import HumanMessage
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
                return {"error": "Failed to generate context plan."}
                
            # Extract the first tool call (ContextPlan)
            plan_args = tool_calls[0]['args']
            
            # Validate against Pydantic model (optional but good practice)
            context_plan = ContextPlan(**plan_args)
            
            logger.info(f"TriageArchitect generated plan with {len(context_plan.actions)} actions.")

            # 5. Return Artifact with recommendations
            return {
                "artifacts": {
                    "context_plan": context_plan.model_dump()
                },
                "scratchpad": {
                    "triage_reasoning": context_plan.reasoning,
                    "recommended_specialists": context_plan.recommended_specialists
                }
            }
            
        except Exception as e:
            logger.error(f"Error in TriageArchitect: {e}", exc_info=True)
            return {"error": str(e)}
