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