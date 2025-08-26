# app/src/graph/state.py
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    Defines the shared state that is passed between all nodes in the graph.
    `Annotated` is used to specify how the state should be updated (e.g., operator.add appends to lists).
    """

    messages: Annotated[List[BaseMessage], operator.add]
    routing_history: Annotated[List[str], operator.add]
    turn_count: int
    task_is_complete: bool
    next_specialist: Optional[str]
    recommended_specialists: Optional[List[str]]
    triage_recommendations: Optional[List[str]]  # New field for preserving triage recommendations.
    text_to_process: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    error: Optional[str]
    error_report: Optional[str]
    json_artifact: Optional[Dict[str, Any]]
    html_artifact: Optional[str]
    critique_artifact: Optional[str]
    system_plan: Optional[Dict[str, Any]]
    archive_report: Optional[str]
    web_builder_iteration: Optional[int]