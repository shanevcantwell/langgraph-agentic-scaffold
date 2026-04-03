"""
Observability API router -- all endpoints for monitoring LAS workflow execution.

This module is mounted by the main FastAPI app via ``app.include_router()``.
Dependencies (workflow_runner, langsmith_client) are injected at startup
via ``init()`` so the router has no import-time coupling to the execution layer.

Endpoints:
    GET  /v1/runs/active           -- discover active run IDs
    GET  /v1/runs/{run_id}/events  -- SSE stream of AG-UI events for a run
    GET  /v1/progress/{run_id}     -- poll intra-node progress entries
    GET  /v1/traces/{run_id}       -- LangSmith trace tree
    GET  /v1/graph/topology        -- static graph structure for Neural Grid
    GET  /v1/archives/{filename}   -- download archive zip
"""
import logging
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse

from .event_bus import event_bus
from .active_runs import active_runs
from ..interface.translator import AgUiTranslator

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Injected dependencies -- set via init() during FastAPI lifespan
# ---------------------------------------------------------------------------

_workflow_runner: Any = None
_langsmith_client: Any = None


def init(
    workflow_runner: Any,
    langsmith_client: Optional[Any] = None,
) -> None:
    """
    Inject runtime dependencies.  Called from api.py lifespan after
    WorkflowRunner and LangSmith client are initialized.
    """
    global _workflow_runner, _langsmith_client
    _workflow_runner = workflow_runner
    _langsmith_client = langsmith_client
    logger.info("Observability router initialized.")


# ---------------------------------------------------------------------------
# Active runs discovery (ADR-UI-003: glue between chat head and obs head)
# ---------------------------------------------------------------------------

@router.get("/v1/runs/active")
def get_active_runs():
    """
    Returns currently active run IDs for observability head discovery.

    This is the glue between the two heads (ADR-UI-003): when a run is initiated
    from an external client (e.g., AnythingLLM via /v1/chat/completions),
    V.E.G.A.S. needs to know the run_id to attach its observability panels.
    """
    return {"runs": active_runs.get_active()}


# ---------------------------------------------------------------------------
# Headless run observation (#267)
# ---------------------------------------------------------------------------

@router.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    """
    SSE endpoint for headless observation of externally-initiated runs (#267).

    V.E.G.A.S. discovers run IDs via ``GET /v1/runs/active`` then connects
    here to receive AG-UI events in real time.  The raw LangGraph events are
    pushed by the chat head's tee and translated to AG-UI format here.
    """
    if not active_runs.contains(run_id):
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    queue = await event_bus.subscribe(run_id)

    async def _generate():
        translator = AgUiTranslator()

        async def _queue_as_stream():
            while True:
                event = await queue.get()
                if event is None:
                    return  # sentinel -- stream ended
                yield event

        async for ag_event in translator.translate(_queue_as_stream()):
            yield f"data: {ag_event.model_dump_json()}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Intra-node progress polling
# ---------------------------------------------------------------------------

@router.get("/v1/progress/{run_id}")
async def get_progress(run_id: str):
    """
    Poll for intra-node progress entries during long-running specialist execution.
    Returns accumulated entries since last poll, then clears them.
    UI polls this every 2-3s while a run is active.
    """
    from ..utils.progress_store import drain
    entries = drain(run_id)
    return {"entries": entries}


# ---------------------------------------------------------------------------
# LangSmith trace tree
# ---------------------------------------------------------------------------

@router.get("/v1/traces/{run_id}")
async def get_run_trace(run_id: str):
    """
    Fetches the LangSmith trace tree for a specific run ID.
    This allows the frontend to visualize the execution details in real-time.
    """
    if not _langsmith_client:
        raise HTTPException(status_code=503, detail="LangSmith client not initialized")

    try:
        runs = list(_langsmith_client.list_runs(trace_id=run_id))
        return {"runs": [r.model_dump() for r in runs]}
    except Exception as e:
        logger.error(f"Failed to fetch traces for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Graph topology (Neural Grid visualization)
# ---------------------------------------------------------------------------

@router.get("/v1/graph/topology")
def get_graph_topology():
    """
    Returns the static structure of the graph for UI visualization.
    Exposes nodes (specialists) and edges (routing relationships).

    Node types:
    - router: The central routing hub
    - core_infrastructure: End, archiver, critic (special graph roles)
    - specialist: User-facing specialists that can be routed to
    - mcp_only: Services accessible only via MCP (not graph nodes)

    Edge types:
    - conditional: Router's dynamic routing decisions
    - completion: Specialist -> Router/END based on task_is_complete
    - terminal: END -> graph termination
    """
    if not _workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")

    from ..workflow.specialist_categories import SpecialistCategories
    from ..enums import CoreSpecialist

    builder = _workflow_runner.builder
    specialists = builder.specialists
    allowed_destinations = builder.allowed_destinations

    # Category mapping for subgraph clustering in UI
    CATEGORY_MAP = {
        # Orchestration & Planning
        "router_specialist": "orchestration",
        "triage_architect": "orchestration",
        "project_director": "orchestration",
        "systems_architect": "planning",
        # Context Engineering
        "facilitator_specialist": "context",
        "dialogue_specialist": "context",
        # Research Pipeline
        "synthesizer_specialist": "research",
        # Chat Subgraph
        "chat_specialist": "chat",
        "progenitor_alpha_specialist": "chat",
        "progenitor_bravo_specialist": "chat",
        "tiered_synthesizer_specialist": "chat",
        "default_responder_specialist": "chat",
        # Data & Analysis
        "text_analysis_specialist": "data",
        # File Operations
        "navigator_specialist": "files",
        "batch_processor_specialist": "files",
        # Builders
        "web_builder": "builders",
        # Distillation (internal subgraph)
        "distillation_coordinator_specialist": "distillation",
        "distillation_prompt_expander_specialist": "distillation",
        "distillation_prompt_aggregator_specialist": "distillation",
        "distillation_response_collector_specialist": "distillation",
        # Utilities
        "prompt_specialist": "utilities",
        "image_specialist": "utilities",
        "prompt_triage_specialist": "utilities",
        # Core Infrastructure
        "end_specialist": "core",
        "archiver_specialist": "core",
        # MCP-only (not graph nodes)
        "summarizer_specialist": "mcp_only",
        "file_specialist": "mcp_only",
    }

    # Build node list with categorization
    nodes = []
    router_name = CoreSpecialist.ROUTER.value
    node_exclusions = SpecialistCategories.get_node_exclusions()

    for name in specialists:
        if name == router_name:
            node_type = "router"
        elif name in SpecialistCategories.CORE_INFRASTRUCTURE:
            node_type = "core_infrastructure"
        elif name in node_exclusions:
            node_type = "mcp_only"
        else:
            node_type = "specialist"

        spec_config = builder.config.get("specialists", {}).get(name, {})
        category = CATEGORY_MAP.get(name, "other")

        nodes.append({
            "id": name,
            "type": node_type,
            "category": category,
            "description": spec_config.get("description", ""),
            "has_llm": spec_config.get("llm_config") is not None,
            "is_graph_node": name not in node_exclusions,
            "is_routable": name in allowed_destinations
        })

    # Build edge list representing the hub-and-spoke architecture
    edges = []

    # Router -> all routable destinations (conditional edges)
    for dest in allowed_destinations:
        edges.append({
            "source": router_name,
            "target": dest,
            "type": "conditional",
            "label": "route"
        })

    # Collect subgraph exclusions for hub-spoke wiring
    subgraph_exclusions = []
    for subgraph in builder.subgraphs:
        subgraph_exclusions.extend(subgraph.get_excluded_specialists())

    hub_spoke_exclusions = SpecialistCategories.get_hub_spoke_exclusions(subgraph_exclusions)

    # Specialists -> Router/END (completion edges)
    end_name = CoreSpecialist.END.value
    for name in specialists:
        if name in hub_spoke_exclusions or name in node_exclusions:
            continue
        edges.append({
            "source": name,
            "target": router_name,
            "type": "completion",
            "label": "continue"
        })
        edges.append({
            "source": name,
            "target": end_name,
            "type": "completion",
            "label": "complete"
        })

    # END -> terminal
    edges.append({
        "source": end_name,
        "target": "__end__",
        "type": "terminal",
        "label": "terminate"
    })

    # Include subgraph info for richer visualization
    subgraph_info = []
    for subgraph in builder.subgraphs:
        subgraph_info.append({
            "name": type(subgraph).__name__,
            "managed_specialists": subgraph.get_excluded_specialists(),
            "router_excluded": subgraph.get_router_excluded_specialists() if hasattr(subgraph, 'get_router_excluded_specialists') else []
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "subgraphs": subgraph_info,
        "entry_point": builder.entry_point,
        "architecture": builder.config.get("architecture", "default")
    }


# ---------------------------------------------------------------------------
# Archive download
# ---------------------------------------------------------------------------

@router.get("/v1/archives/{filename}")
async def download_archive(filename: str):
    """
    Serves archive zip files for download.
    Uses AGENTIC_SCAFFOLD_ARCHIVE_PATH env var (same as ArchiverSpecialist).
    """
    # Security: only allow .zip files and prevent path traversal
    if not filename.endswith(".zip") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    archive_path = os.getenv("AGENTIC_SCAFFOLD_ARCHIVE_PATH", "./logs/archive")
    archive_dir = Path(os.path.expanduser(archive_path))
    file_path = archive_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archive not found")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/zip"
    )
