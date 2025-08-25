from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from langchain_core.messages import AIMessage


class CodeWriterSpecialist(BaseSpecialist):
    """A specialist that writes Python code based on a user's request."""

    def __init__(self, specialist_name: str):
        """
        Initializes the specialist.

        The specialist_name is passed in by the ChiefOfStaff and must
        match the key in config.yaml.
        """
        super().__init__(specialist_name)

    def _execute_logic(self, state: dict) -> dict:
        """
        Core logic of the CodeWriterSpecialist.

        The BaseSpecialist.execute() handles logging and boilerplate.
        Here we just focus on invoking the LLM and processing the output.
        """
        # 1. Get the message history from the state
        messages = state["messages"]

        # 2. Wrap messages in a standardized LLM request
        request = StandardizedLLMRequest(messages=messages)

        # 3. Call the LLM adapter
        response_data = self.llm_adapter.invoke(request)

        # 4. Extract the AI response
        ai_response_content = response_data.get(
            "text_response",
            "I am unable to provide a response at this time."
        )
        ai_message = AIMessage(content=ai_response_content)

        # 5. Return the new message (SpecialistHub will append it)
        return {"messages": [ai_message]}
