# app/src/graph/state.py
import operator
from typing import TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated

from langchain_core.messages import BaseMessage


class GraphState(TypedDict):
    """
    Represents the entire state of the agentic graph.
    This TypedDict is the single source of truth for the data that flows
    between nodes in the workflow.
    """

    # The `Annotated` type with `operator.add` is the key to robust state
    # management. It tells LangGraph to append new messages to the existing list,
    # rather than replacing it. This is the correct way to manage conversational
    # history.
    messages: Annotated[List[BaseMessage], operator.add]

    # The name of the specialist that the router has decided should run next.
    next_specialist: Optional[str]

    # --- Artifacts & Data ---
    # These fields hold the data and artifacts produced by specialists.
    text_to_process: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    json_artifact: Optional[Dict[str, Any]]
    html_artifact: Optional[str]
    system_plan: Optional[Dict[str, Any]]
    recommended_specialists: Optional[List[str]]
    critique_artifact: Optional[str]
    archive_report: Optional[str]

    # --- Control Flow & Metadata ---
    error: Optional[str]
    turn_count: int
    task_is_complete: bool
    web_builder_iteration: Optional[int]