# app/src/specialists/helpers.py
import logging
from typing import Dict, Any, Optional
from langchain_core.messages import AIMessage
from ..llm.adapter import BaseAdapter

logger = logging.getLogger(__name__)

def create_missing_artifact_response(
    specialist_name: str,
    required_artifact: str,
    recommended_specialist: str,
    guidance: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a standardized "self-correction" response when a required artifact is missing.

    This helper function generates a log message, a user-facing AIMessage, and a
    recommendation for the router, making the agent more robust.
    """
    error_message = (
        f"I am the {specialist_name}. I cannot run because the required artifact "
        f"'{required_artifact}' is missing from the state. I am suggesting that the "
        f"'{recommended_specialist}' should run to create it."
    )
    if guidance:
        error_message += f" {guidance}"
    logger.warning(f"{specialist_name} was called without '{required_artifact}'. Suggesting {recommended_specialist}.")

    ai_message = AIMessage(content=error_message, name=specialist_name)

    return {
        "messages": [ai_message],
        "recommended_specialists": [recommended_specialist]
    }

def create_llm_message(
    specialist_name: str,
    llm_adapter: Optional[BaseAdapter],
    content: str,
    additional_kwargs: Optional[Dict[str, Any]] = None
) -> AIMessage:
    """
    Creates a standardized AIMessage from an LLM-based specialist, automatically
    including the model name for traceability in the final report.
    """
    final_kwargs = additional_kwargs.copy() if additional_kwargs else {}
    
    llm_name = llm_adapter.model_name if llm_adapter and hasattr(llm_adapter, 'model_name') else None
    if llm_name:
        final_kwargs["llm_name"] = llm_name
        
    return AIMessage(
        content=content, name=specialist_name, additional_kwargs=final_kwargs
    )