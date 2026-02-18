# app/src/graph/state.py
import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, ConfigDict
from langchain_core.messages import BaseMessage

class DistillationState(TypedDict):
    """
    State for federated distillation workflows.

    Manages multi-phase distillation across knowledge domains with graph-driven iteration.
    See ADR-DISTILL-002 for complete state management patterns.
    """

    # Domain iteration
    domains: List[str]                       # e.g., ["agentic_architecture", "devenv_tooling", ...]
    current_domain: str                      # e.g., "agentic_architecture"
    domain_index: int                        # 0-based index in domains list

    # Prompt management
    seed_prompts: List[str]                  # Current domain's seed prompts (loaded once per domain)
    expanded_prompts: List[str]              # Accumulated variations for current domain

    # Iteration tracking (graph-driven iteration via conditional edges)
    expansion_index: int                     # Index of next seed to expand
    collection_index: int                    # Index of next prompt to collect

    # Progress tracking
    seeds_processed: int                     # Total seeds expanded so far
    responses_collected: int                 # Total responses collected so far (successful only)
    error_count: int                         # Total errors across all phases

    # Phase control
    current_phase: str                       # "expansion" | "response_collection" | "persistence"

    # File tracking
    temp_dataset_path: Optional[str]         # Path to temp JSONL file being written
    completed_dataset_paths: List[str]       # Paths to finalized domain datasets

    # Configuration (from coordinator config or user input)
    variations_per_seed: int                 # e.g., 3
    output_dir: str                          # e.g., "/workspace/datasets" 

class Artifacts(BaseModel):
    """A Pydantic model for all possible artifacts generated during a workflow."""
    model_config = ConfigDict(extra="allow")

    final_user_response_md: Optional[str] = None
    archive_report_md: Optional[str] = None
    task_plan: Optional[Dict[str, Any]] = None       # Issue #171: SA entry point produces this
    system_plan: Optional[Dict[str, Any]] = None      # WebBuilder's implementation plan (via SA MCP)
    html_document_html: Optional[str] = None
    # text_to_process REMOVED: Already handled via artifacts dict (runner.py puts file content in artifacts["text_to_process"])
    text_analysis_report_md: Optional[str] = None
    json_artifact: Optional[Dict[str, Any]] = None
    uploaded_image_png: Optional[str] = None

class Scratchpad(BaseModel):
    """
    A Pydantic model for all transient data used during a workflow.

    Transient fields moved from root GraphState (per ADR-CORE-004 and Task 2.7):
    - recommended_specialists: Optional[List[str]] - Routing recommendations from specialists/triage
    - error_report: Optional[str] - Error details from failed specialist executions

    These fields are accessed via state["scratchpad"].get("field_name") and set via
    update["scratchpad"] = {"field_name": value} to work with LangGraph's ior reducer.
    """
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    user_response_snippets: List[str] = []
    extraction_schema: Optional[Any] = None
    target_artifact_name: Optional[str] = None
    termination_reason: Optional[str] = None

    # Loop recovery state (ADR-CORE-016: Menu Filter Pattern - Tier 1)
    forbidden_specialists: Optional[List[str]] = None
    """
    Transient list of specialists forbidden from next routing decision.
    Populated by InvariantMonitor when loop detected (immediate repetition or 2-step cycle).
    Cleared after successful specialist execution (non-router) to prevent permanent bans.
    Implements hard constraint (P=0) by removing specialists from router's tool schema.
    """
    loop_detection_reason: Optional[str] = None
    """Diagnostic message explaining why specialists were forbidden."""

    # Progressive loop detection (stagnation check)
    output_hashes: Optional[Dict[str, List[str]]] = None
    """
    Tracks output hashes per specialist for stagnation detection.
    Structure: {specialist_name: [hash1, hash2, hash3]} (last 3 hashes)
    Used to distinguish productive iteration (different outputs) from stuck loops (same output).
    Cleared when routing to different specialist (context switch).
    """

def reduce_parallel_tasks(current: List[str], update: List[str] | str) -> List[str]:
    """
    Reducer for managing active parallel tasks.
    - If update is a list, it REPLACES the current list (initialization).
    - If update is a string, it REMOVES that string from the current list (completion).
    """
    if isinstance(update, list):
        return update
    if isinstance(update, str):
        if update in current:
            new_list = current.copy()
            new_list.remove(update)
            return new_list
    return current

def reduce_signals(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """
    ADR-077: Replace reducer for routing signals.

    Each write is a complete snapshot — stale signals don't linger via accumulation.
    If a node doesn't write to signals (update is None), the current state is preserved.
    """
    if update is None:
        return current
    return update


class GraphState(TypedDict):
    """
    Defines the shared state that is passed between all nodes in the graph.
    `Annotated` is used to specify how the state should be updated (e.g., operator.add appends to lists).
    """

    # --- Core Orchestration State ---
    messages: Annotated[List[BaseMessage], operator.add]
    routing_history: Annotated[List[str], operator.add]
    turn_count: int
    # operator.or_ reducer: if ANY parallel branch signals complete, task is complete.
    # Required because parallel fan-out (e.g., tiered chat progenitors) may both write this key.
    task_is_complete: Annotated[bool, operator.or_]
    next_specialist: Optional[str]

    # --- LLM Trace Capture (Training Data) ---
    # Accumulates raw LLM prompt/response traces for fine-tuning datasets.
    # Written to llm_traces.jsonl in the archive by ArchiverSpecialist.
    llm_traces: Annotated[List[Dict[str, Any]], operator.add]

    # --- State Timeline (Observability) ---
    # Accumulates full state snapshots at each specialist boundary.
    # Write-only: no specialist reads this back. Emitted via SSE as
    # STATE_SNAPSHOT events and written to state_timeline.jsonl in archive.
    # Includes prompts, IM decisions, and react traces for debugging.
    state_timeline: Annotated[List[Dict[str, Any]], operator.add]

    # --- Parallel Execution State (Task 3.3) ---
    # Tracks currently active parallel tasks for scatter-gather synchronization.
    parallel_tasks: Annotated[List[str], reduce_parallel_tasks]

    # --- Generic State Management ---
    # Use `artifacts` for significant data outputs such as complete files or image base64,
    # and `scratchpad` for transient state.
    artifacts: Annotated[Dict[str, Any], operator.ior]
    scratchpad: Annotated[Dict[str, Any], operator.ior]

    # --- Routing Signals (ADR-077: Signal Processor Architecture) ---
    # Complete snapshot of routing-relevant signals. Written by specialists (PD, SafeExecutor CB),
    # consumed by SignalProcessorSpecialist. Uses replace reducer (not ior) — each write is a
    # full snapshot, preventing stale signals from lingering via accumulation.
    signals: Annotated[Dict[str, Any], reduce_signals]

    # --- Specialist-Specific State REMOVED (Task 2.7: State Purge) ---
    # The following fields have been MIGRATED to scratchpad (see Scratchpad model above):
    #   - recommended_specialists: Optional[List[str]] → scratchpad["recommended_specialists"]
    #   - error_report: Optional[str] → scratchpad["error_report"]
    # This enforces architectural purity per ADR-CORE-004.

    # --- Distillation Workflow State ---
    # State for federated distillation workflows.
    # Uses operator.ior reducer to merge dictionary updates from specialists.
    # See ADR-DISTILL-002 for complete state management patterns.
    distillation_state: Annotated[Optional[DistillationState], operator.ior]

    # --- Convening Architecture State (ADR-CORE-023) ---
    manifest_path: Optional[str]
    active_branch_id: Optional[str]
    fishbowl_active: Optional[bool]
    synthesis_pending: Optional[bool]
    hitl_required: Optional[bool]
