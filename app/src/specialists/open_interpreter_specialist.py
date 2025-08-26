# app/src/specialists/open_interpreter_specialist.py

from typing import Dict, Any
from .wrapped_code_specialist import WrappedCodeSpecialist
from langchain_core.messages import AIMessage

class OpenInterpreterSpecialist(WrappedCodeSpecialist):
    """
    A wrapper specialist for the Open Interpreter agent. It can execute
    code locally to accomplish complex tasks.
    """

    def _translate_state_to_input(self, state: Dict[str, Any]) -> Any:
        """Translates the GraphState to the Open Interpreter's input format."""
        messages = state.get("messages", [])
        if not messages:
            raise ValueError("OpenInterpreterSpecialist cannot execute with an empty message history.")
        return messages[-1].content

    def _translate_output_to_state(self, state: dict, output: Any) -> Dict[str, Any]:
        """Translates the Open Interpreter's output back to the GraphState format."""
        ai_message = AIMessage(content=str(output), name=self.specialist_name)
        return {"messages": [ai_message]}