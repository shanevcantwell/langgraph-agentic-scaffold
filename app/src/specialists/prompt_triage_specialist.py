# app/src/specialists/prompt_triage_specialist.py
import logging
from typing import Dict, Any, List, Literal

from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel, Field

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class TriageResult(BaseModel):
    """A Pydantic model to guide the LLM's JSON output for prompt triage."""
    sentiment: Literal["positive", "negative", "neutral"] = Field(..., description="The overall sentiment of the user's prompt.")
    coherence: Literal["coherent", "unclear", "fragment"] = Field(..., description="Describes the clarity of the user's prompt (e.g., a complete thought, a fragment, or requiring clarification).")
    is_actionable: bool = Field(..., description="Whether the prompt is clear and specific enough to be acted upon by other specialists.")
    estimated_complexity: Literal["simple", "complex"] = Field(..., description="An estimation of the request's complexity. 'simple' for direct questions or single actions, 'complex' for multi-step tasks requiring planning.")
    reasoning: str = Field(..., description="A brief, user-facing explanation for the classification, especially if not actionable.")

class PromptTriageSpecialist(BaseSpecialist):
    """
    A specialist that performs an initial analysis of the user's prompt to ensure it is clear and actionable.
    It analyzes the user's initial prompt for sentiment, coherence, and actionability.
    """

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        messages: List[BaseMessage] = state["messages"]

        request = StandardizedLLMRequest(
            messages=messages, output_model_class=TriageResult
        )
        response_data = self.llm_adapter.invoke(request)
        json_response = response_data.get("json_response")

        if not json_response:
            raise ValueError("PromptTriageSpecialist failed to get a valid JSON response from the LLM.")

        triage_result = TriageResult(**json_response)

        if not triage_result.is_actionable:
            # If the prompt is not actionable, create a user-facing message and
            # set the task_is_complete flag to halt the workflow gracefully.
            report = f"I am unable to proceed with the request. Reason: {triage_result.reasoning}"
            return {"messages": [AIMessage(content=report, name=self.specialist_name)], "task_is_complete": True}
        else:
            # If the prompt is fine, add a note to the history and let the graph proceed to the router.
            report = f"Initial prompt analysis complete. Sentiment: {triage_result.sentiment}, Coherence: {triage_result.coherence}. Passing to router for planning."
            return {"messages": [AIMessage(content=report, name=self.specialist_name)], "json_artifact": json_response}
