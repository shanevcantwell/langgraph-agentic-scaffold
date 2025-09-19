# In: app/src/strategies/critique/llm_strategy.py

from app.src.graph.state import GraphState
from app.src.llm.adapter import BaseAdapter, StandardizedLLMRequest
from app.src.specialists.schemas import Critique
from app.src.utils.prompt_loader import load_prompt
from langchain_core.messages import SystemMessage, HumanMessage
from .base import BaseCritiqueStrategy

class LLMCritiqueStrategy(BaseCritiqueStrategy):
    def __init__(self, llm_adapter: BaseAdapter, prompt_file: str):
        """
        Initializes the strategy with its dependencies.

        Args:
            llm_adapter: An instance of a system-level LLM adapter for communication.
            prompt_file: The filename of the system prompt to be used for the critique.
        """
        self.llm_adapter = llm_adapter
        self.system_prompt = load_prompt(prompt_file)

    def critique(self, state: GraphState) -> Critique:
        """
        Performs a critique using an LLM. It builds a rich context from the
        GraphState and invokes the LLM to get a structured critique.
        """
        html_artifact = state.get("artifacts", {}).get("html_document.html")

        if not html_artifact:
            # This is the corrected, robust error-handling path.
            return Critique(
                decision="REVISE",
                overall_assessment="Cannot perform critique: html_document.html is missing.",
                points_for_improvement=["The required 'html_document.html' artifact was not found in the state."],
                positive_feedback=[]
            )

        # Use the payload (state) to build a rich context for the LLM
        contextual_messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Original User Goal: {state['messages'][0].content}"),
            HumanMessage(content=f"Critique the following HTML:\n\n```html\n{html_artifact}\n```")
        ]

        request = StandardizedLLMRequest(
            messages=contextual_messages,
            output_model_class=Critique
        )
        
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            # Handle the case where the LLM fails to return valid JSON
            return Critique(
                decision="REVISE",
                overall_assessment="LLM failed to provide a structured critique.",
                points_for_improvement=[f"The LLM response could not be parsed into the required format. Raw response: {response_data.get('text_response')}"],
                positive_feedback=[]
            )

        return Critique(**json_response)
