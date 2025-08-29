# app/src/specialists/helpers.py
from typing import Dict, Any, Optional

from langchain_core.messages import AIMessage
from ..llm.adapter import BaseAdapter


def create_llm_message(
    specialist_name: str,
    llm_adapter: Optional[BaseAdapter],
    content: str,
    additional_kwargs: Optional[Dict[str, Any]] = None,
) -> AIMessage:
    """Creates a standardized AIMessage with metadata about the LLM used."""
    # Initialize with any provided kwargs to support flexible metadata.
    final_kwargs = additional_kwargs.copy() if additional_kwargs else {}

    model_name = "unknown_model"
    if llm_adapter:
        # Correctly access the model_name property instead of a method.
        model_name = llm_adapter.model_name

    # Add the llm_name, which is a standard piece of metadata we want on all messages.
    final_kwargs.setdefault("llm_name", model_name)

    return AIMessage(
        content=content,
        name=specialist_name,
        additional_kwargs=final_kwargs,
    )


def create_missing_artifact_response(
    specialist_name: str,
    missing_artifact: str,
    recommended_specialist: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a standardized response when a required artifact is missing from the state.

    This response is designed to be interpreted by the Router, which can then
    use the recommendation to self-correct the workflow.
    """
    ai_message_content = f"I, {specialist_name}, cannot execute. The required artifact '{missing_artifact}' is missing from the current state. The workflow must be re-routed to a specialist capable of generating this artifact before I can proceed."
    ai_message = AIMessage(content=ai_message_content, name=specialist_name)

    response = {"messages": [ai_message]}
    if recommended_specialist:
        response["recommended_specialists"] = [recommended_specialist]

    return response