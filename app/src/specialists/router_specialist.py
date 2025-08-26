# src/specialists/router_specialist.py
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
        description=f"The specialist to route to next. Must be one of the AVAILABLE SPECIALISTS listed in the prompt, or '{END}' if the task is complete."
    )

class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
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

        request = StandardizedLLMRequest(messages=final_messages, tools=[Route])
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls or not tool_calls[0].get('args'):
            logger.error("Router LLM failed to produce a valid tool call. Attempting to route to Archiver for a final report.")
            if CoreSpecialist.ARCHIVER.value in self.specialist_map:
                next_specialist = CoreSpecialist.ARCHIVER.value
                content = "Router failed to select a valid next specialist. Routing to ArchiverSpecialist for a final report."
            else:
                next_specialist = END
                content = "Router failed to select a valid next specialist and Archiver is not available. Ending workflow."
            return {"next_specialist": next_specialist, "tool_calls": [], "content": content}
        
        next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist', END)
        
        valid_options = list(current_specialists.keys())
        if next_specialist_from_llm not in valid_options and next_specialist_from_llm != END:
            logger.warning(f"Router LLM returned an invalid specialist: '{next_specialist_from_llm}'. Valid options are {valid_options + [END]}. Routing to END.")
            next_specialist_from_llm = END
        
        if next_specialist_from_llm == END and CoreSpecialist.ARCHIVER.value in self.specialist_map:
            logger.info("Router LLM chose to end. Rerouting to ArchiverSpecialist for final report.")
            next_specialist_from_llm = CoreSpecialist.ARCHIVER.value
        
        content = f"Routing to specialist: {next_specialist_from_llm}"
        return {"next_specialist": next_specialist_from_llm, "tool_calls": tool_calls, "content": content}

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        next_specialist_name = ""
        routing_type = ""
        content = ""
        tool_calls = []
        update = {}

        # The router's decision logic is now a clear, prioritized if/elif/else block.
        # This makes the flow of control much easier to follow and maintain.
        if error_message := state.get("error"):
            routing_type = "error_signal"
            content = f"An error occurred: {error_message}. Routing to ArchiverSpecialist for final report."
            next_specialist_name = CoreSpecialist.ARCHIVER.value if CoreSpecialist.ARCHIVER.value in self.specialist_map else END

        elif state.get("task_is_complete", False):
            routing_type = "completion_signal"
            content = "Task is complete. Routing to ArchiverSpecialist for final report."
            next_specialist_name = CoreSpecialist.ARCHIVER.value if CoreSpecialist.ARCHIVER.value in self.specialist_map else END

        elif recommended := state.get("recommended_specialists"):
            if len(recommended) == 1 and recommended[0] in self.specialist_map:
                routing_type = "recommendation"
                next_specialist_name = recommended[0]
                content = f"Proceeding with recommended specialist: {next_specialist_name}"
            else:
                # If the recommendation is invalid or ambiguous, fall back to the LLM.
                llm_decision = self._get_llm_choice(state)
                routing_type = "llm_decision"
                next_specialist_name = llm_decision["next_specialist"]
                content = llm_decision["content"]
                tool_calls = llm_decision.get("tool_calls", [])
        else:
            # Default to LLM-based routing if no other signals are present.
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

        logger.info(f"Router decision: Routing to {next_specialist_name}")

        # By centralizing the state update here, we ensure consistency across all routing paths.
        update.update({
            "messages": [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "recommended_specialists": None, # Always consume recommendations after the router has run.
            "routing_history": [next_specialist_name]
        })
        return update
