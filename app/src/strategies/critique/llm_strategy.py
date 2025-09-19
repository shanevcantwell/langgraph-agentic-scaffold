import logging
from pydantic import ValidationError
from app.src.graph.state import GraphState
from app.src.llm.adapter import BaseAdapter, StandardizedLLMRequest
from app.src.specialists.schemas import Critique, SpecialistOutput, StatusEnum
from app.src.utils.prompt_loader import load_prompt
from langchain_core.messages import SystemMessage, HumanMessage
from .base import BaseCritiqueStrategy

logger = logging.getLogger(__name__)

class LLMCritiqueStrategy(BaseCritiqueStrategy):
    def __init__(self, llm_adapter: BaseAdapter, prompt_file: str):
        self.llm_adapter = llm_adapter
        self.system_prompt = load_prompt(prompt_file)

    def critique(self, state: GraphState) -> SpecialistOutput[Critique]:
        html_artifact = state.get("artifacts", {}).get("html_document.html")

        if not html_artifact:
            return SpecialistOutput[Critique](
                status=StatusEnum.FAILURE,
                rationale="Cannot perform critique: The required 'html_document.html' artifact was not found in the state.",
                payload=None
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
        
        if not json_response:
            raw_text = response_data.get("text_response", "[No text response available]")
            rationale = f"The LLM adapter could not produce a valid structured response. Raw text from LLM: {raw_text}"
            logger.warning(rationale)
            return SpecialistOutput[Critique](status=StatusEnum.FAILURE, rationale=rationale, payload=None)

        try:
            critique_payload = Critique(**json_response)
            return SpecialistOutput[Critique](
                status=StatusEnum.SUCCESS,
                rationale="Critique generated successfully.",
                payload=critique_payload
            )
        except ValidationError as e:
            rationale = f"The LLM produced a structurally valid JSON, but it did not match the required schema for a Critique. Details: {e}"
            logger.error(rationale)
            return SpecialistOutput[Critique](status=StatusEnum.FAILURE, rationale=rationale, payload=None)
