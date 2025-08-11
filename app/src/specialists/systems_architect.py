from langchain_core.messages import HumanMessage
from ..utils.prompt_loader import load_prompt
from .base import BaseSpecialist


class SystemsArchitect(BaseSpecialist):
    """
    A specialist that generates a Mermaid.js diagram script.
    """

    def __init__(self, llm_provider):
        system_prompt = load_prompt("systems_architect")
        super().__init__(llm_provider=llm_provider, system_prompt=system_prompt)

    def execute(self, state: dict) -> dict:
        """
        Takes the goal from the state, invokes the LLM to generate a Mermaid diagram,
        and returns the code to update the state.
        """
        print("---SYSTEMS ARCHITECT: Generating Mermaid Code---")
        goal = state.get("original_goal")
        if not goal:
            return {"error": "Goal not found in state."}

        user_prompt = f"Here is the workflow to diagram: {goal}"
        response = self.invoke(user_prompt)

        mermaid_code = self._parse_llm_response(response)
        return {"mermaid_code": mermaid_code}
