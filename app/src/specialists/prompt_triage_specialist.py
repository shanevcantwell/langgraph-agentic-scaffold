# app/src/specialists/prompt_triage_specialist.py
import logging
from typing import Dict, Any, List

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, Field

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class TriageResult(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for prompt triage."""
    is_actionable: bool = Field(..., description="Whether the prompt is clear and specific enough to be acted upon.")
    reasoning: str = Field(..., description="A brief, user-facing explanation for the actionability assessment.")
    recommended_specialists: List[str] = Field(
        default_factory=list,
        description="A list of specialist names that are most relevant to fulfilling the user's request. This list should be ordered by relevance."
    )

class PromptTriageSpecialist(BaseSpecialist):
    """
    A specialist that acts as a "Semantic Recommender". It analyzes the user's
    initial prompt against the known capabilities of all other specialists and
    recommends a list of relevant specialists for the Router to use.
    """
    def __init__(self, specialist_name: str):
        super().__init__(specialist_name)
        self.specialist_map: Dict[str, Dict] = {}

    def set_specialist_map(self, specialist_configs: Dict[str, Dict]):
        """Receives the full map of specialist configurations from the orchestrator."""
        # Exclude self from the map
        self.specialist_map = {k: v for k, v in specialist_configs.items() if k != self.specialist_name}
        logger.info(f"TriageSpecialist now aware of all other specialist configurations.")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]

        # Dynamically build the list of available specialists for the prompt
        available_specialists_desc = [f"- {name}: {conf.get('description', 'No description.')}" for name, conf in self.specialist_map.items()]
        specialist_list_str = "\n".join(available_specialists_desc)
        contextual_prompt = (
            f"Given the user's request, analyze it and recommend the most relevant specialists from the following list to complete the task. "
            f"Return a ranked list of their names.\n\nAvailable Specialists:\n{specialist_list_str}"
        )

        request = StandardizedLLMRequest(
            messages=messages + [AIMessage(content=contextual_prompt)],
            output_model_class=TriageResult
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("TriageSpecialist failed to get a valid JSON response from the LLM.")

        triage_result = TriageResult(**json_response)

        if not triage_result.is_actionable:
            report = f"I am unable to proceed with the request. Reason: {triage_result.reasoning}"
            return {"messages": [AIMessage(content=report, name=self.specialist_name)], "task_is_complete": True}
        else:
            report = "Initial prompt analysis complete. Passing recommendations to the router."
            logger.info(f"Triage complete. Recommending specialists: {triage_result.recommended_specialists}")

            return {"messages": [AIMessage(content=report, name=self.specialist_name)],
                    "recommended_specialists": triage_result.recommended_specialists}
