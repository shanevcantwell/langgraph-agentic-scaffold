# src/specialists/router_specialist.py
import logging
from typing import Dict, Any, List
from enum import Enum
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
        self.available_specialists: List[str] = []
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from ChiefOfStaff).")

    def set_available_specialists(self, specialist_names: List[str]):
        """Receives the list of available specialists from the orchestrator to enable validation."""
        self.available_specialists = specialist_names
        logger.info(f"Router now aware of specialists: {self.available_specialists}")

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

        # --- SUGGESTION CHECK ---
        # Check if a previous specialist suggested the next step. This makes the
        # workflow more deterministic and less reliant on the LLM for simple transitions.
        if suggested_next := state.get("suggested_next_specialist"):
            if suggested_next in self.available_specialists:
                logger.info(f"Using suggested next specialist: {suggested_next}")
                ai_message = AIMessage(content=f"Proceeding with suggested specialist: {suggested_next}")
                return {
                    "messages": [ai_message],
                    "next_specialist": suggested_next,
                    "turn_count": turn_count,
                    "suggested_next_specialist": None # Consume the suggestion
                }
            else:
                logger.warning(f"Ignoring invalid suggestion for next specialist: {suggested_next}")

        # --- ROUTING LOGIC ---
        messages: List[BaseMessage] = state["messages"][:] # Make a copy
        # The router should make decisions based on the conversation history and tool calls,
        # not the raw data artifacts. The 'text_to_process' is a payload for the *next*
        # specialist, not context for the router itself. This prevents cluttering the
        # router's context window and keeps its reasoning focused on orchestration.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[Route]
        )
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        # If the model fails to return a valid tool call, end the workflow gracefully
        # and record the failure in the message history.
        if not tool_calls or not tool_calls[0].get('args'):
            logger.warning("Router LLM did not return a valid tool call. Ending workflow.")
            next_specialist = END
            ai_message = AIMessage(content="Router failed to select a valid next specialist. Ending workflow.")
        else:
            next_specialist_from_llm = tool_calls[0]['args'].get('next_specialist', END)

            # --- VALIDATION ---
            # Check if the LLM's choice is a valid, known specialist.
            # This prevents KeyErrors in the graph if the LLM hallucinates a name.
            if next_specialist_from_llm not in self.available_specialists and next_specialist_from_llm != END:
                logger.warning(f"Router LLM returned an invalid specialist: '{next_specialist_from_llm}'. Valid options are {self.available_specialists + [END]}. Routing to END.")
                next_specialist = END
                ai_message = AIMessage(content=f"Router attempted to route to an unknown specialist '{next_specialist_from_llm}'. Halting workflow.")
            else:
                next_specialist = next_specialist_from_llm
                # Create an AIMessage that records the successful tool call.
                ai_message = AIMessage(content="", tool_calls=tool_calls)
        
        logger.info(f"Router decision: Routing to {next_specialist}")

        # CORRECTED: Return a dictionary with all state updates.
        # LangGraph will merge this into the global state.
        return {
            # Return only the new message to be appended to the state.
            "messages": [ai_message],
            "next_specialist": next_specialist,
            "turn_count": turn_count,
            "suggested_next_specialist": None # Always consume/clear the suggestion after the router has run.
        }
