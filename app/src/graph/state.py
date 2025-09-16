# app/src/graph/state.py
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    Defines the shared state that is passed between all nodes in the graph.
    `Annotated` is used to specify how the state should be updated (e.g., operator.add appends to lists).
    """

    # --- Core Orchestration State ---
    messages: Annotated[List[BaseMessage], operator.add]
    routing_history: Annotated[List[str], operator.add]
    turn_count: int
    task_is_complete: bool
    next_specialist: Optional[str]

    # --- Generic State Management ---
    # Use `artifacts` for significant data outputs such as complete files or image base64,
    # and `scratchpad` for transient state. 
    artifacts: Dict[str, Any]
    scratchpad: Dict[str, Any]

    # --- Specialist-Specific State ---
    # These fields are used by specific specialists and are candidates for
    # migration to the `artifacts` or `scratchpad` dictionaries in the future.
    recommended_specialists: Optional[List[str]]
    triage_recommendations: Optional[List[str]] 
    text_to_process: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    error_report: Optional[str]
    system_plan: Optional[Dict[str, Any]]
    web_builder_iteration: Optional[int]
    user_response: Optional[str] # The final, synthesized response for the user.