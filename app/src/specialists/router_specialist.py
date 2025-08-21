import logging
from typing import Dict, Any, List, Literal
from enum import Enum
from langgraph.graph import END
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class AvailableSpecialists(str, Enum):
    """Dynamically create an Enum of available specialists plus a finish state."""
    # Load specialist names from config to make the tool dynamic
    # This is a local import to avoid potential circular dependencies at the module level.
    config = ConfigLoader().get_config()
    specialist_names = {name: name for name in config.get("specialists", {})}
    
    # Add the mandatory finish state
    finish = END
    
    # Create the Enum
    locals().update(specialist_names)


class Route(BaseModel):
    """Select the next specialist to route to or finish the conversation."""
    next_specialist: AvailableSpecialists = Field(
        ...,
        description=f"The specialist to route to next, or '{END}' if the user's request has been fully addressed."
    )


class RouterSpecialist(BaseSpecialist):
    """
    A specialist that routes the conversation to the appropriate specialist
    or ends the conversation if the goal has been met.
    """

    def __init__(self, specialist_name: str = "router_specialist"):
        # The complex __init__ logic has been moved to the ChiefOfStaff.
        # The router is now a "plain" specialist that gets its context-aware
        # adapter injected by the orchestrator during the "morning standup".
        super().__init__(specialist_name)
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from ChiefOfStaff).")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # Check if a previous specialist has already set the next_specialist
        if state.get("next_specialist"):
            # Clear the next_specialist from the state to avoid infinite loops
            # if the target specialist doesn't clear it.
            next_specialist_from_state = state["next_specialist"]
            state["next_specialist"] = None # Clear it for the next routing decision
            logger.info(f"Router decision: Prioritizing next_specialist from state: {next_specialist_from_state}")
            return {"next_specialist": next_specialist_from_state}

        messages: List[BaseMessage] = state["messages"]

        # Create a standardized request to the Language Model.
        # We provide the `Route` model as a tool for the LLM to call.
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[Route]
        )

        # Invoke the LLM adapter.
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls:
            logger.warning("Router LLM did not return a tool call. Defaulting to finish.")
            return {"next_specialist": END}

        # Extract the routing decision from the tool call.
        next_specialist = tool_calls[0]['args'].get('next_specialist', END)
        logger.info(f"Router decision: Routing to {next_specialist}")

        # The ChiefOfStaff will interpret this output to direct the graph.
        return {"next_specialist": next_specialist}