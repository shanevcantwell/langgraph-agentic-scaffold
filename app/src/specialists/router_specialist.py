# app/src/specialists/router_specialist.py

import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import END
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from .base import BaseSpecialist
from .helpers import create_llm_message
from ..llm.adapter import StandardizedLLMRequest
from ..enums import CoreSpecialist

logger = logging.getLogger(__name__)

class Route(BaseModel):
    # By changing from a dynamic Enum to a simple string, we generate a much simpler
    # JSON schema. This helps bypass potential bugs in the LLM server's grammar
    # engine, which can be sensitive to complex schemas with enum constraints.
    next_specialist: str = Field(
        ...,
        description="The specialist to route to next. Must be one of the AVAILABLE SPECIALISTS listed in the prompt."
    )

class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.specialist_map: Dict[str, Dict] = {}
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from ChiefOfStaff).")

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the full map of specialist configurations from the orchestrator."""
        self.specialist_map = {k: v for k, v in specialist_configs.items() if k != self.specialist_name}
        logger.info(f"Router now aware of all specialist configurations.")

    def _get_llm_choice(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Invokes the LLM to get the next specialist and returns the validated decision."""
        messages: List[BaseMessage] = state["messages"][:]  # Make a copy
        recommended_specialists = state.get("recommended_specialists")

        if recommended_specialists:
            current_specialists = {name: self.specialist_map[name] for name in recommended_specialists if name in self.specialist_map}
            logger.info(f"Filtering router choices based on Triage recommendations: {list(current_specialists.keys())}")
        else:
            current_specialists = self.specialist_map

        if not current_specialists:
            logger.warning("Router has no specialists to choose from after filtering. Ending workflow.")
            return {"next_specialist": END, "content": "No specialists available to route to. Ending workflow."}

        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in current_specialists.items()]
        tools_list_str = "\n".join(available_tools_desc)
        contextual_prompt_addition = f"Based on the current context, you MUST choose a specialist from the following list:\n{tools_list_str}"
        
        final_messages = messages + [SystemMessage(content=contextual_prompt_addition)]

        request = StandardizedLLMRequest(messages=final_messages, tools=[Route], force_tool_call=True)
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist') if tool_calls and tool_calls[0].get('args') else None

        if not next_specialist_from_llm:
            logger.error("Router LLM failed to produce a valid tool call. Attempting to fall back to a default handler.")
            # Fallback Priority: 1. Default Responder, 2. Archiver, 3. End
            if CoreSpecialist.DEFAULT_RESPONDER.value in self.specialist_map:
                next_specialist = CoreSpecialist.DEFAULT_RESPONDER.value
                content = "Router failed to select a valid next specialist. Routing to DefaultResponderSpecialist."
            elif CoreSpecialist.ARCHIVER.value in self.specialist_map:
                next_specialist = CoreSpecialist.ARCHIVER.value
                content = "Router failed to select a valid next specialist. Routing to ArchiverSpecialist for a final report."
            else:
                next_specialist = CoreSpecialist.END.value
                content = "Router failed to select a valid next specialist and no fallback handlers are available. Routing to EndSpecialist."
            return {"next_specialist": next_specialist, "tool_calls": [], "content": content}
        
        valid_options = list(current_specialists.keys())
        if next_specialist_from_llm not in valid_options:
            logger.warning(f"Router LLM returned an invalid specialist: '{next_specialist_from_llm}'. Valid options are {valid_options}. Falling back to DefaultResponder.")
            next_specialist_from_llm = CoreSpecialist.DEFAULT_RESPONDER.value
        
        content = f"Routing to specialist: {next_specialist_from_llm}"
        return {"next_specialist": next_specialist_from_llm, "tool_calls": tool_calls, "content": content}

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        next_specialist_name = ""
        routing_type = ""
        content = ""
        tool_calls = []

        # The router's primary role is to use its LLM to make a decision.
        # It will filter its choices based on recommendations, but the final
        # decision is always made by the LLM for consistency.
        llm_decision = self._get_llm_choice(state)
        routing_type = "llm_decision"
        next_specialist_name = llm_decision["next_specialist"]
        content = llm_decision["content"]
        tool_calls = llm_decision.get("tool_calls", [])

        ai_message = create_llm_message(
            specialist_name=self.specialist_name,
            llm_adapter=self.llm_adapter,
            content=content,
            additional_kwargs={
                "routing_decision": next_specialist_name,
                "routing_type": routing_type,
                "tool_calls": tool_calls,
            },
        )

        logger.info(f"Router decision: Routing to {next_specialist_name} (Type: {routing_type})")

        current_messages = state.get("messages", [])
        current_routing_history = state.get("routing_history", [])
        # By centralizing the state update here, we ensure consistency across all routing paths.
        return {
            "messages": current_messages + [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "recommended_specialists": None, # Always consume recommendations after the router has run.
            "routing_history": current_routing_history + [next_specialist_name]
        }
