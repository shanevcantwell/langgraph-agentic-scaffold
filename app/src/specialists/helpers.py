from typing import Dict, Any, Optional, List

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
    missing_artifacts: List[str],
    recommended_specialists: List[str]
) -> dict:
    """
    Generates a standardized response when required artifacts are missing from the state.

    This response informs the user, provides a self-correction recommendation to the
    router, and prevents the specialist from executing with incomplete data.
    """
    missing_list = ", ".join(f"'{a}'" for a in missing_artifacts)
    content = (
        f"I, {specialist_name}, cannot execute because the following required artifacts "
        f"are missing from the current state: {missing_list}. "
        f"I recommend running the following specialist(s) first: {', '.join(recommended_specialists)}."
    )
    ai_message = AIMessage(content=content, name=specialist_name)
    return {"messages": [ai_message], "recommended_specialists": recommended_specialists}