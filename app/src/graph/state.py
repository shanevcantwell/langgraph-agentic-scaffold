# app/src/graph/state.py
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel
from langchain_core.messages import BaseMessage

class Dossier(TypedDict):
    recipient: str
    payload_key: str 
    message: Optional[str] 

class Artifacts(BaseModel):
    """A Pydantic model for all possible artifacts generated during a workflow."""
    final_user_response_md: Optional[str] = None
    archive_report_md: Optional[str] = None
    system_plan: Optional[Dict[str, Any]] = None
    critique_md: Optional[str] = None
    html_document_html: Optional[str] = None
    text_to_process: Optional[str] = None
    text_analysis_report_md: Optional[str] = None
    json_artifact: Optional[Dict[str, Any]] = None
    uploaded_image_png: Optional[str] = None

    class Config:
        extra = 'allow' # Allow other keys for flexibility

class Scratchpad(BaseModel):
    """A Pydantic model for all transient data used during a workflow."""
    user_response_snippets: List[str] = []
    critique_decision: Optional[str] = None
    extraction_schema: Optional[Any] = None
    target_artifact_name: Optional[str] = None
    web_builder_iteration: Optional[int] = None

    class Config:
        extra = 'allow'
        arbitrary_types_allowed = True

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
    artifacts: Annotated[Dict[str, Any], operator.ior]
    scratchpad: Annotated[Dict[str, Any], operator.ior]

    # --- Specialist-Specific State ---
    # These fields are used by specific specialists and are candidates for
    # migration to the `artifacts` or `scratchpad` dictionaries in the future.
    recommended_specialists: Optional[List[str]]
    error_report: Optional[str]
