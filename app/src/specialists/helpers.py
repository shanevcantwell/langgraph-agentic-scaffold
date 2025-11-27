from typing import Dict, Any, Optional, List

from langchain_core.messages import AIMessage, HumanMessage
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

def create_error_message(
    error_content: str,
    recommended_specialists: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Creates a standardized dictionary for returning an error message and
    re-routing recommendations from a specialist.
    """
    message = AIMessage(
        content=error_content,
        name="error_handler",
        additional_kwargs={"is_error": True},
    )

    state_update: Dict[str, Any] = {"messages": [message]}

    # Task 2.7: recommended_specialists moved to scratchpad
    if recommended_specialists:
        state_update["scratchpad"] = {"recommended_specialists": recommended_specialists}

    return state_update


def create_decline_response(
    specialist_name: str,
    reason: str,
    recommended_specialists: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Creates a response indicating this specialist cannot handle the current task.

    The "not me" pattern: A specialist can decline a task and remove itself from
    the recommended_specialists list. The Router will detect this and re-route
    to the next available specialist.

    Args:
        specialist_name: The name of the specialist declining the task
        reason: Why this specialist cannot handle the task
        recommended_specialists: Optional list of specialists to try instead.
                                 If not provided, the Router will use remaining
                                 recommendations or call the LLM for a new decision.

    Returns:
        State update dict with decline_task signal in scratchpad

    Example:
        if not self._can_handle_task(state):
            return create_decline_response(
                specialist_name=self.specialist_name,
                reason="This task requires vision capabilities I don't have",
                recommended_specialists=["vision_specialist"]
            )
    """
    message = AIMessage(
        content=f"[{specialist_name}] I cannot handle this task: {reason}",
        name=specialist_name,
        additional_kwargs={"is_decline": True},
    )

    scratchpad: Dict[str, Any] = {
        "decline_task": True,
        "decline_reason": reason,
        "declining_specialist": specialist_name,
    }

    if recommended_specialists:
        scratchpad["recommended_specialists"] = recommended_specialists

    return {
        "messages": [message],
        "scratchpad": scratchpad,
    }