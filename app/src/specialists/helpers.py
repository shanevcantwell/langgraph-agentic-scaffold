# app/src/specialists/helpers.py
import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)

def create_missing_artifact_response(
    specialist_name: str,
    required_artifact: str,
    recommended_specialist: str
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
    logger.warning(f"{specialist_name} was called without '{required_artifact}'. Suggesting {recommended_specialist}.")

    ai_message = AIMessage(content=error_message, name=specialist_name)

    return {
        "messages": [ai_message],
        "recommended_specialists": [recommended_specialist]
    }