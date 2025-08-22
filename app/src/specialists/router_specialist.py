# src/specialists/router_specialist.py
import logging
from typing import Dict, Any, List
from enum import Enum
from langgraph.graph import END
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)

class AvailableSpecialists(str, Enum):
    config = ConfigLoader().get_config()
    specialist_names = {name: name for name in config.get("specialists", {})}
    finish = END
    locals().update(specialist_names)

class Route(BaseModel):
    next_specialist: AvailableSpecialists = Field(
        ...,
        description=f"The specialist to route to next, or '{END}' if the user's request has been fully addressed."
    )

class RouterSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        logger.info("Initialized RouterSpecialist (awaiting contextual configuration from ChiefOfStaff).")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # --- STATE MANAGEMENT ---
        # The router node is now responsible for managing the turn count.
        turn_count = state.get("turn_count", 0) + 1
        logger.debug(f"Executing turn {turn_count}")

        # --- ROUTING LOGIC ---
        messages: List[BaseMessage] = state["messages"]
        request = StandardizedLLMRequest(
            messages=messages,
            tools=[Route]
        )
        response_data = self.llm_adapter.invoke(request)
        tool_calls = response_data.get("tool_calls", [])

        if not tool_calls:
            logger.warning("Router LLM did not return a tool call. Defaulting to prompt_specialist.")
            next_specialist = "prompt_specialist"
        else:
            next_specialist = tool_calls[0]['args'].get('next_specialist', END)
        
        logger.info(f"Router decision: Routing to {next_specialist}")

        # CORRECTED: Return a dictionary with all state updates.
        # LangGraph will merge this into the global state.
        return {
            "next_specialist": next_specialist,
            "turn_count": turn_count
        }
