# src/specialists/router_specialist.py
import logging
from typing import Dict, Any, List, Optional
from langgraph.graph import END
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.config_loader import ConfigLoader

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

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # --- STATE MANAGEMENT ---
        # The router node is now responsible for managing the turn count.
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        # --- COMPLETION CHECK ---
        # If a previous specialist has signaled that the task is complete,
        # bypass the LLM and route directly to the end.
        if state.get("task_is_complete"):
            logger.info("A specialist has signaled task completion. Routing to END.")
            return {"next_specialist": END, "turn_count": turn_count}

        # --- RECOMMENDATION CHECK (Two-Stage Routing) ---
        recommended_specialists = state.get("recommended_specialists")

        # 1. Deterministic Handoff: If exactly one specialist is recommended, route directly.
        if recommended_specialists and len(recommended_specialists) == 1:
            next_specialist = recommended_specialists[0]
            if next_specialist in self.specialist_map:
                logger.info(f"Using deterministic recommendation for next specialist: {next_specialist}")
                ai_message = AIMessage(
                    content=f"Proceeding with recommended specialist: {next_specialist}",
                    name=self.specialist_name,
                    additional_kwargs={"routing_decision": next_specialist, "routing_type": "recommendation"}
                )
                return {
                    "messages": [ai_message],
                    "next_specialist": next_specialist,
                    "turn_count": turn_count,
                    "recommended_specialists": None  # Consume the recommendation
                }
            else:
                logger.warning(f"Ignoring invalid recommendation for specialist: {next_specialist}")

        # 2. LLM-based Choice (Filtered or Full)
        messages: List[BaseMessage] = state["messages"][:] # Make a copy

        if recommended_specialists:
            # Use the recommended list to filter choices for the LLM
            current_specialists = {name: self.specialist_map[name] for name in recommended_specialists if name in self.specialist_map}
            logger.info(f"Filtering router choices based on Triage recommendations: {list(current_specialists.keys())}")
        else:
            # Fallback to all available specialists
            current_specialists = self.specialist_map

        # If, after filtering, there are no specialists available, end the workflow.
        if not current_specialists:
            logger.warning("Router has no specialists to choose from after filtering. Ending workflow.")
            return {
                "messages": [AIMessage(content="No specialists available to route to. Ending workflow.", name=self.specialist_name)],
                "next_specialist": END,
                "turn_count": turn_count
            }

        # Dynamically build the tool list for the prompt
        available_tools_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in current_specialists.items()]
        tools_list_str = "\n".join(available_tools_desc)
        contextual_prompt_addition = f"Based on the current context, you MUST choose a specialist from the following list:\n{tools_list_str}"
        
        final_messages = messages + [SystemMessage(content=contextual_prompt_addition)]

        request = StandardizedLLMRequest(
            messages=final_messages,
            tools=[Route]
        )
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        # If the model fails to return a valid tool call, end the workflow gracefully
        # and record the failure in the message history.
        if not tool_calls or not tool_calls[0].get('args'):
            logger.warning("Router LLM did not return a valid tool call. Ending workflow.")
            next_specialist_name = END
            ai_message = AIMessage(
                content="Router failed to select a valid next specialist. Ending workflow.",
                name=self.specialist_name,
                additional_kwargs={"routing_decision": END, "routing_type": "llm_failure"}
            )
        else:
            next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist', END)

            # --- VALIDATION ---
            # Check if the LLM's choice is a valid, known specialist.
            valid_options = list(current_specialists.keys())
            if next_specialist_from_llm not in valid_options and next_specialist_from_llm != END:
                logger.warning(f"Router LLM returned an invalid specialist: '{next_specialist_from_llm}'. Valid options are {valid_options + [END]}. Routing to END.")
                next_specialist_name = END
                ai_message = AIMessage(
                    content=f"Router attempted to route to an unknown specialist '{next_specialist_from_llm}'. Halting workflow.",
                    name=self.specialist_name,
                    additional_kwargs={"routing_decision": END, "invalid_route_attempt": next_specialist_from_llm}
                )
            else:
                next_specialist_name = next_specialist_from_llm
                # Create an AIMessage that records the successful tool call and explicitly states the destination.
                content = f"Routing to specialist: {next_specialist_name}" if next_specialist_name != END else "Task is complete. Routing to END."
                ai_message = AIMessage(
                    content=content,
                    tool_calls=tool_calls,
                    name=self.specialist_name,
                    additional_kwargs={"routing_decision": next_specialist_name, "routing_type": "llm_success"}
                )
        
        logger.info(f"Router decision: Routing to {next_specialist_name}")

        # CORRECTED: Return a dictionary with all state updates.
        # LangGraph will merge this into the global state.
        return {
            # Return only the new message to be appended to the state.
            "messages": [ai_message],
            "next_specialist": next_specialist_name,
            "turn_count": turn_count,
            "recommended_specialists": None  # Always consume/clear the recommendation after the router has run.
        }
