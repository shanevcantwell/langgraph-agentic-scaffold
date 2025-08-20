# src/graph/state.py

from typing import TypedDict, Annotated, List, Optional, Dict, Any
from langchain_core.messages import BaseMessage
import operator

class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        messages: A list of messages that form the conversation.
                  The `Annotated` type hint with `operator.add` ensures that
                  new messages are always appended to the list.
        next_specialist: The name of the specialist to route to next.
        text_to_process: Text that a specialist may need to process.
        extracted_data: The structured data extracted by the data extractor.
        error: An error message, if any.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    next_specialist: Optional[str]
    text_to_process: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    error: Optional[str]
    json_artifact: Optional[str]
    html_artifact: Optional[str]
    system_plan: Optional[Dict[str, Any]] # Added system_plan

