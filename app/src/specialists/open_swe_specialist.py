# app/src/specialists/open_swe_specialist.py

from .wrapped_specialist import WrappedSpecialist
from langchain_core.messages import AIMessage

class OpenSweSpecialist(WrappedSpecialist):
    """A wrapper specialist for the open-swe agent."""

    def _translate_state_to_input(self, state: dict) -> any:
        """Translates the GraphState to the open-swe agent's input format."""
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("OpenSweSpecialist cannot execute with an empty message history.")
        return messages[-1].content

    def _translate_output_to_state(self, state: dict, output: any) -> dict:
        """Translates the open-swe agent's output back to the GraphState format."""
        ai_message = AIMessage(content=str(output))
        return {"messages": state["messages"] + [ai_message]}
