import logging
from app.src.graph.state import GraphState
from app.src.llm.adapter import BaseAdapter, StandardizedLLMRequest
from app.src.specialists.schemas import Critique
from app.src.utils.prompt_loader import load_prompt
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import ValidationError
from .base import BaseCritiqueStrategy

logger = logging.getLogger(__name__)

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
            return Critique(
                decision="REVISE",
                overall_assessment="Cannot perform critique: html_document.html is missing.",
                points_for_improvement=["The required 'html_document.html' artifact was not found in the state."],
                positive_feedback=[],
                is_parse_error=True # A missing artifact is a condition for retry/reroute
            )

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

        # --- MODIFICATION: Add explicit type validation ---
        # This check enforces the contract that the strategy requires a dictionary (mapping)
        # to instantiate the Pydantic model. It protects against the LLM returning a
        # JSON array, which the adapter would parse into a list or tuple.
        if not isinstance(json_response, dict):
            logger.warning(f"LLM adapter returned a non-dictionary type: {type(json_response).__name__}. Expected a dict.")
            return Critique(
                decision="REVISE",
                overall_assessment="LLM returned an invalid data structure.",
                points_for_improvement=[
                    f"The LLM was expected to return a JSON object (a dictionary), but it returned a different structure (e.g., a list or tuple).",
                    f"Data received: {json_response}"
                ],
                positive_feedback=[],
                is_parse_error=True
            )
        # --- END MODIFICATION ---

        if len(json_response) == 1:
            first_key = next(iter(json_response))
            if isinstance(json_response[first_key], dict):
                logger.warning(f"LLM returned a nested dictionary under key '{first_key}'. Unwrapping to use the inner dictionary.")
                json_response = json_response[first_key]

        try:
            return Critique(**json_response)
        except ValidationError as e:
            logger.warning(f"LLM returned data that failed Pydantic validation: {e}. Raw JSON: {json_response}")
            return Critique(
                decision="REVISE",
                overall_assessment="LLM returned malformed data that failed validation.",
                points_for_improvement=[
                    f"The LLM's structured response was missing required fields or had incorrect data types. Validation Error: {e}",
                    f"Problematic JSON received from LLM: {json_response}"
                ],
                positive_feedback=[],
                is_parse_error=True
            )
