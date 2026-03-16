# app/src/api.py
# --- Environment Variable Loading ---
# This MUST be the first import and execution, to ensure that all subsequent
# modules have access to the environment variables.
from dotenv import load_dotenv
load_dotenv()
print("Environment variables from .env file loaded.")

from typing import Dict, List, Optional, Any
import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
import gradio as gr
from .workflow.runner import WorkflowRunner
from .utils.errors import WorkflowError
from .utils.cancellation_manager import CancellationManager
from langsmith import Client
from .interface.translator import AgUiTranslator
from .interface.openai_schema import ChatCompletionRequest
from .interface.openai_request_adapter import translate_request
from .interface.openai_response_formatter import format_sync_response
from .interface.openai_translator import OpenAiTranslator

langsmith_client: Optional[Client] = None
logger = logging.getLogger(__name__)

workflow_runner: WorkflowRunner | None = None


# ---------------------------------------------------------------------------
# Event Bus — broadcast raw LangGraph events to headless observers (#267)
# ---------------------------------------------------------------------------

class _EventBus:
    """
    Pub/sub for raw LangGraph events keyed by run_id.

    Producers call push() for each event.  Observers call subscribe() to get
    an asyncio.Queue, then read from it.  A sentinel ``None`` is pushed on
    close() to signal end-of-stream.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def push(self, run_id: str, event: Dict[str, Any]) -> None:
        async with self._lock:
            for q in self._subscribers.get(run_id, []):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # slow observer — drop event rather than block producer

    async def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers.setdefault(run_id, []).append(q)
        return q

    async def close(self, run_id: str) -> None:
        """Push sentinel and remove all subscribers for *run_id*."""
        async with self._lock:
            queues = self._subscribers.pop(run_id, [])
        for q in queues:
            try:
                q.put_nowait(None)  # sentinel
            except asyncio.QueueFull:
                pass

_event_bus = _EventBus()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifecycle for startup and shutdown events.
    """
    global langsmith_client, workflow_runner
    workflow_runner = WorkflowRunner()

    # ADR-CORE-042: Enable checkpointing for interrupt/resume ("Raise Hand" pattern)
    # This allows specialists to pause workflow and request user clarification
    from .persistence.checkpoint_manager import get_default_checkpointer
    checkpointer = get_default_checkpointer()
    if checkpointer:
        workflow_runner.set_async_checkpointer(checkpointer)
        logger.info("--- FastAPI startup: Checkpointer enabled for interrupt/resume. ---")

    # Initialize external MCP services (Docker containers like filesystem)
    # This must be called after WorkflowRunner init to connect containers
    try:
        await workflow_runner.builder.initialize_external_mcp()
        logger.info("--- FastAPI startup: External MCP services initialized. ---")
    except Exception as e:
        logger.error(f"Failed to initialize external MCP services: {e}", exc_info=True)
        # Non-fatal if services are marked as not required

    try:
        # This will respect the environment variables (LANGCHAIN_TRACING_V2, etc.)
        langsmith_client = Client()
        logger.info("--- FastAPI startup: LangSmith client initialized successfully. ---")
    except Exception as e:
        logger.error(f"Failed to initialize LangSmith client on startup: {e}", exc_info=True)
        langsmith_client = None

    yield

    # Cleanup external MCP containers on shutdown
    try:
        await workflow_runner.builder.cleanup_external_mcp()
        logger.info("--- FastAPI shutdown: External MCP services cleaned up. ---")
    except Exception as e:
        logger.error(f"Error during external MCP cleanup: {e}", exc_info=True)

    if langsmith_client:
        # On shutdown, give the LangSmith client a moment to send any buffered traces.
        logger.info("--- FastAPI shutdown: Allowing 2s for LangSmith trace flush... ---")
        import time
        time.sleep(2)

# --- FastAPI Application ---
app = FastAPI(
    title="Agentic System API",
    description="An API for interacting with the LangGraph-based multi-agent system.",
    version="1.0.0",
    lifespan=lifespan
)

# --- Data Contracts ---
from pydantic import BaseModel, Field
class InvokeRequest(BaseModel):
    input_prompt: str = Field(
        ...,
        description="The initial user prompt to send to the agentic graph.",
        examples=["What is the capital of France?"]
    )
    text_to_process: Optional[str] = Field(
        None,
        description="Optional text content to be processed (e.g., from an uploaded file).",
        examples=["This is the content of a document."]
    )
    image_to_process: Optional[str] = Field(
        None,
        description="Optional base64-encoded image to be processed.",
        examples=["data:image/png;base64,iVBORw0KGgo..."]
    )
    use_simple_chat: bool = Field(
        False,
        description="If True, use simple chat mode (single ChatSpecialist). If False (default), use tiered chat mode (parallel progenitors)."
    )
    # ADR-CORE-075: Conversation context continuity
    conversation_id: Optional[str] = Field(
        None,
        description="Links turns in a multi-turn conversation. Returned by server on first turn."
    )
    prior_messages: Optional[List[dict]] = Field(
        None,
        description="Prior conversation turns as [{role: 'user'|'assistant', content: str}]. Last 3 pairs used."
    )
    # ADR-CORE-045: Subagent mode for fork() invocations
    subagent: bool = Field(
        False,
        description="When True, this invocation is a child of another LAS workflow via fork(). "
                    "Skips archiver and EI gate; returns concise result instead of full state."
    )
    # #203: Fork cancellation propagation
    parent_run_id: Optional[str] = Field(
        None,
        description="Run ID of the parent workflow that spawned this child via fork(). "
                    "Used to register parent→child relationship for cascade cancellation."
    )

class InvokeResponse(BaseModel):
    final_output: Dict[str, Any] = Field(
        ...,
        description="The final output from the graph's END state."
    )

class ConfigUpdateRequest(BaseModel):
    default_llm_config: Optional[str] = Field(
        None,
        description="The key of the LLM provider to set as default (e.g., 'lmstudio_router', 'gemini_pro')."
    )

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "API is running"}

@app.get("/v1/system/llm-providers")
def get_llm_providers():
    """
    Returns a list of available LLM providers and the current default.
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")
    
    config = workflow_runner.config
    providers = config.get("llm_providers", {})
    default_config = config.get("workflow", {}).get("default_llm_config")
    
    # Return a simplified list for the UI
    provider_list = []
    for key, data in providers.items():
        provider_list.append({
            "key": key,
            "type": data.get("type"),
            "model": data.get("model_name", "Unknown"),
            "is_default": key == default_config
        })
        
    return {
        "providers": provider_list,
        "current_default": default_config
    }

@app.post("/v1/system/config")
def update_system_config(request: ConfigUpdateRequest):
    """
    Updates the system configuration at runtime.
    Currently supports switching the default LLM provider.
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")
    
    overrides = {}
    if request.default_llm_config:
        # Validate that the provider exists
        current_config = workflow_runner.config
        if request.default_llm_config not in current_config.get("llm_providers", {}):
            raise HTTPException(status_code=400, detail=f"Provider '{request.default_llm_config}' not found in configuration.")
        
        overrides["default_llm_config"] = request.default_llm_config
        
    if overrides:
        try:
            workflow_runner.reload(overrides)
            return {"status": "Configuration updated and workflow reloaded", "overrides": overrides}
        except Exception as e:
            logger.error(f"Failed to reload workflow: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to reload workflow: {str(e)}")
    
    return {"status": "No changes requested"}

async def _stream_formatter(generator):
    """
    This internal generator formats the raw output from the workflow runner
    into the specific JSON structure the Gradio UI expects.
    """
    accumulated_state = None
    current_thread_id = None  # ADR-CORE-042: Track for interrupt handling

    async for chunk in generator:
        # Check for run_id chunk (emitted first)
        if "run_id" in chunk:
            yield f"data: {json.dumps({'run_id': chunk['run_id']})}\n\n"
            continue

        # ADR-CORE-075: Forward conversation_id to client for multi-turn threading
        if "conversation_id" in chunk:
            yield f"data: {json.dumps({'conversation_id': chunk['conversation_id']})}\n\n"
            continue

        # ADR-CORE-042: Capture thread_id for interrupt handling
        if "thread_id" in chunk:
            current_thread_id = chunk["thread_id"]
            continue

        # ADR-CORE-042: Detect interrupt event ("Raise Hand" pattern)
        # When a specialist calls interrupt(), LangGraph yields {"__interrupt__": [...]}
        if "__interrupt__" in chunk:
            interrupt_data = chunk["__interrupt__"]
            if interrupt_data and len(interrupt_data) > 0:
                # Extract the interrupt payload (questions, context, etc.)
                payload = interrupt_data[0].value if hasattr(interrupt_data[0], 'value') else interrupt_data[0].get("value", {})
                yield f"data: {json.dumps({'interrupt': payload, 'thread_id': current_thread_id, 'resumable': True})}\n\n"
            return  # End stream - UI will call /resume endpoint

        # The raw stream from LangGraph is a dictionary where keys are node names.
        # We can inspect this to provide real-time status updates.
        for node_name, node_output in chunk.items():
            # When a specialist node is invoked, its output is nested under its name.
            # We can use this event to send a status update to the UI.
            if isinstance(node_output, dict):
                # Emit status update for EVERY specialist execution (not just message-emitting ones)
                status_update = f"Executing specialist: {node_name}..."
                # ALSO send "Entering node:" format for UI timing tracking
                logs_update = f"Entering node: {node_name}"
                yield f"data: {json.dumps({'status': status_update, 'logs': logs_update})}\n\n"

                # Check for errors (Issue #70: both error and error_report now in scratchpad)
                # GraphState doesn't define top-level "error" field, so it must live in scratchpad
                scratchpad = node_output.get("scratchpad", {})
                if isinstance(scratchpad, dict):
                    error_msg = scratchpad.get("error", "")
                    error_report = scratchpad.get("error_report", "")
                    if error_msg or error_report:
                        # Stream error immediately with both message and full report
                        yield f"data: {json.dumps({'error': error_msg or 'Unknown error', 'error_report': error_report})}\n\n"

                # Stream scratchpad reasoning fields in real-time for THOUGHT STREAM visibility
                if isinstance(scratchpad, dict):
                    reasoning_fields = {k: v for k, v in scratchpad.items()
                                       if k.endswith('_reasoning') or k.endswith('_decision')}
                    if reasoning_fields:
                        yield f"data: {json.dumps({'scratchpad': reasoning_fields, 'source': node_name})}\n\n"

                # Accumulate state deltas according to GraphState reducer semantics
                if accumulated_state is None:
                    accumulated_state = {}
                    for key, value in node_output.items():
                        if isinstance(value, list):
                            accumulated_state[key] = list(value)
                        elif isinstance(value, dict):
                            accumulated_state[key] = dict(value)
                        else:
                            accumulated_state[key] = value
                else:
                    # Merge node_output into accumulated_state following GraphState reducers
                    for key, value in node_output.items():
                        if key in ["messages", "routing_history", "llm_traces", "state_timeline"]:
                            # operator.add: append to lists
                            accumulated_state.setdefault(key, []).extend(value if isinstance(value, list) else [value])
                        elif key in ["artifacts", "scratchpad"]:
                            # operator.ior: merge dictionaries
                            accumulated_state.setdefault(key, {}).update(value if isinstance(value, dict) else {})
                        else:
                            # No annotation: overwrite with latest value
                            accumulated_state[key] = value

                # Emit state_snapshot events for timeline entries
                for timeline_entry in node_output.get("state_timeline", []):
                    yield f"data: {json.dumps({'state_snapshot': timeline_entry})}\n\n"

    # After the main loop, send the accumulated final state with artifacts
    if accumulated_state:
        artifacts = accumulated_state.get("artifacts", {})
        archive_report = artifacts.get("archive_report.md", "")
        html_content = artifacts.get("html_document.html", "")

        # Build a JSON-safe summary of the final state (not the full state with complex objects)
        scratchpad = accumulated_state.get("scratchpad", {})
        messages = accumulated_state.get("messages", [])

        # Convert messages to JSON-safe format (just content and role)
        messages_summary = []
        for msg in messages:
            if hasattr(msg, 'content') and hasattr(msg, 'type'):
                messages_summary.append({
                    "type": msg.type,
                    "content": msg.content[:200] + "..." if len(str(msg.content)) > 200 else msg.content
                })

        # Task 2.7: recommended_specialists and error_report moved to scratchpad
        # Issue #70: error message also in scratchpad (GraphState doesn't have top-level error)
        final_state_summary = {
            "routing_history": accumulated_state.get("routing_history", []),
            "turn_count": accumulated_state.get("turn_count", 0),
            "task_is_complete": accumulated_state.get("task_is_complete", False),
            "next_specialist": accumulated_state.get("next_specialist"),
            "recommended_specialists": scratchpad.get("recommended_specialists") if isinstance(scratchpad, dict) else None,
            "error": scratchpad.get("error") if isinstance(scratchpad, dict) else None,
            "error_report": scratchpad.get("error_report") if isinstance(scratchpad, dict) else None,
            "artifacts": list(artifacts.keys()) if artifacts else [],
            "scratchpad": {k: (v if not isinstance(v, (dict, list)) or len(str(v)) < 500 else f"<{type(v).__name__} with {len(v)} items>") for k, v in scratchpad.items()},
            "messages_summary": messages_summary
        }

        yield f"data: {json.dumps({
            'status': 'Workflow complete.',
            'final_state': final_state_summary,
            'archive': archive_report,
            'html': html_content
        })}\n\n"
    else:
        yield f"data: {json.dumps({'status': 'Workflow complete.'})}\n\n"

@app.get("/v1/traces/{run_id}")
async def get_run_trace(run_id: str):
    """
    Fetches the LangSmith trace tree for a specific run ID.
    This allows the frontend to visualize the execution details in real-time.
    """
    if not langsmith_client:
        raise HTTPException(status_code=503, detail="LangSmith client not initialized")
    
    try:
        # Fetch all runs associated with this trace ID (run_id is used as trace_id in runner)
        runs = list(langsmith_client.list_runs(trace_id=run_id))
        return {"runs": [r.model_dump() for r in runs]}
    except Exception as e:
        logger.error(f"Failed to fetch traces for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/graph/cancel/{run_id}")
async def cancel_run(run_id: str):
    """
    Requests cancellation of a running workflow.
    """
    logger.info(f"Received cancellation request for run_id: {run_id}")
    CancellationManager.request_cancellation(run_id)
    return {"status": "Cancellation requested"}


@app.get("/v1/graph/topology")
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
    - completion: Specialist → Router/END based on task_is_complete
    - terminal: END → graph termination
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")

    from .workflow.specialist_categories import SpecialistCategories
    from .enums import CoreSpecialist

    builder = workflow_runner.builder
    specialists = builder.specialists
    allowed_destinations = builder.allowed_destinations

    # Category mapping for subgraph clustering in UI
    # Based on functional groupings from config.yaml
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
        # Browser (disabled — pending surf-mcp integration)
        # "navigator_browser_specialist": "browser",
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
        # Determine node type
        if name == router_name:
            node_type = "router"
        elif name in SpecialistCategories.CORE_INFRASTRUCTURE:
            node_type = "core_infrastructure"
        elif name in node_exclusions:
            node_type = "mcp_only"
        else:
            node_type = "specialist"

        # Get basic config info for the node
        spec_config = builder.config.get("specialists", {}).get(name, {})

        # Assign category for subgraph clustering (default to "other")
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

    # Router → all routable destinations (conditional edges)
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

    # Specialists → Router/END (completion edges)
    end_name = CoreSpecialist.END.value
    for name in specialists:
        if name in hub_spoke_exclusions or name in node_exclusions:
            continue
        # Each specialist can route back to router or to end
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

    # END → terminal
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


class ResumeRequest(BaseModel):
    """ADR-CORE-018: Request body for resuming interrupted workflows."""
    thread_id: str = Field(
        ...,
        description="The thread ID of the interrupted workflow (from interrupt payload)."
    )
    user_input: str = Field(
        ...,
        description="The user's response to the clarification questions."
    )


@app.post("/v1/graph/resume")
async def resume_workflow(request: ResumeRequest):
    """
    ADR-CORE-042: Resume a workflow from an interrupt point via SSE stream.

    Streams the resumed execution through the same SSE pipe as the initial
    run, so the UI receives routing events, specialist execution, and
    thought stream entries for the post-clarification portion of the graph.
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")

    logger.info(f"Received streaming resume request for thread_id: {request.thread_id}")

    try:
        raw_stream = workflow_runner.resume_streaming(
            thread_id=request.thread_id,
            user_input=request.user_input
        )
        return StreamingResponse(
            _standard_stream_formatter(raw_stream),
            media_type="text/event-stream",
        )
    except ValueError as e:
        logger.error(f"Resume failed - checkpointing disabled: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Resume failed with exception: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resume workflow: {e}")


@app.post("/v1/graph/stream")
async def stream_graph(request: InvokeRequest):
    """Streams the workflow execution step by step."""
    try:
        logger.info(f"Received request to stream graph with prompt: '{request.input_prompt}'")
        raw_stream = workflow_runner.run_streaming(
            goal=request.input_prompt,
            text_to_process=request.text_to_process,
            image_to_process=request.image_to_process,
            use_simple_chat=request.use_simple_chat,
            conversation_id=request.conversation_id,
            prior_messages=request.prior_messages,
        )
        return StreamingResponse(
            _stream_formatter(raw_stream),
            media_type="text/event-stream",
        )
    except WorkflowError as e:
        logger.error(f"Workflow streaming error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow streaming error: {e}")

@app.post("/v1/graph/invoke", response_model=InvokeResponse)
def invoke_graph(request: InvokeRequest):
    try:
        # #203: Generate run_id for sync invocations + register parent-child for fork()
        child_run_id = str(uuid.uuid4())
        if request.parent_run_id:
            CancellationManager.register_child(request.parent_run_id, child_run_id)
            logger.info(f"Fork invocation: child={child_run_id}, parent={request.parent_run_id}")

        logger.info(f"Received sync request to invoke graph with prompt: '{request.input_prompt}'"
                     f"{' (subagent)' if request.subagent else ''}"
                     f" run_id={child_run_id}")
        final_state = workflow_runner.run(
            goal=request.input_prompt,
            text_to_process=request.text_to_process,
            image_to_process=request.image_to_process,
            use_simple_chat=request.use_simple_chat,
            subagent=request.subagent,
            run_id=child_run_id,
        )

        # Task 2.7: error_report moved to scratchpad
        scratchpad = final_state.get("scratchpad", {})
        if error_report := (scratchpad.get("error_report") if isinstance(scratchpad, dict) else None):
            logger.error("Workflow ended with an error. Returning error report.")
            return InvokeResponse(final_output={"error_report": error_report})

        # ADR-CORE-045: Subagent mode returns concise result, not full state
        if request.subagent:
            artifacts = final_state.get("artifacts", {})
            concise = artifacts.get("final_user_response.md", "")
            if not concise:
                messages = final_state.get("messages", [])
                if messages:
                    last = messages[-1]
                    concise = last.get("content", "") if isinstance(last, dict) else str(getattr(last, "content", ""))
            return InvokeResponse(final_output={"result": concise or ""})

        # Normal mode: return full state
        return InvokeResponse(final_output=final_state)

    except WorkflowError as e:
        logger.error(f"Workflow execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution error: {e}")
    finally:
        # #203: Cleanup cancellation state for sync invocations
        CancellationManager.clear_cancellation(child_run_id)

async def _standard_stream_formatter(generator):
    """
    Formats the raw output into standardized AG-UI events (SSE).
    """
    translator = AgUiTranslator()
    async for event in translator.translate(generator):
        # Convert Pydantic model to JSON string
        yield f"data: {event.model_dump_json()}\n\n"

@app.post("/v1/graph/stream/events")
async def stream_graph_events(request: InvokeRequest):
    """
    Streams the workflow execution using the standardized AG-UI event schema.
    This endpoint exposes the AgUiEmitter's output using Server-Sent Events (SSE).
    """
    try:
        logger.info(f"Received request to stream standardized events with prompt: '{request.input_prompt}'")
        raw_stream = workflow_runner.run_streaming(
            goal=request.input_prompt,
            text_to_process=request.text_to_process,
            image_to_process=request.image_to_process,
            use_simple_chat=request.use_simple_chat,
            conversation_id=request.conversation_id,
            prior_messages=request.prior_messages,
        )
        return StreamingResponse(
            _standard_stream_formatter(raw_stream),
            media_type="text/event-stream",
        )
    except WorkflowError as e:
        logger.error(f"Workflow streaming error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow streaming error: {e}")


## ---------------------------------------------------------------------------
## Chat Head — OpenAI-compatible endpoints (ADR-UI-003: Two-Headed Architecture)
## ---------------------------------------------------------------------------

# Track active run IDs for observability head discovery (GET /v1/runs/active)
_active_runs: Dict[str, Any] = {}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """
    OpenAI-compatible chat completion endpoint.

    Supports both streaming (stream: true) and non-streaming (stream: false).
    Produces spec-compliant responses with no vendor extensions.

    The model field is a routing profile selector (e.g., 'las-default', 'las-simple').
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")

    kwargs = translate_request(request)
    logger.info(f"OpenAI chat completion: model={request.model}, stream={request.stream}, goal='{kwargs['goal'][:80]}'")

    if request.stream:
        return await _openai_stream(request, kwargs)
    else:
        return await _openai_sync(request, kwargs)


async def _openai_sync(request: ChatCompletionRequest, kwargs: Dict[str, Any]):
    """Handle non-streaming chat completion."""
    try:
        run_id = str(uuid.uuid4())
        _active_runs[run_id] = {"model": request.model, "status": "running"}

        final_state = workflow_runner.run(
            goal=kwargs["goal"],
            text_to_process=kwargs.get("text_to_process"),
            image_to_process=kwargs.get("image_to_process"),
            use_simple_chat=kwargs.get("use_simple_chat", False),
            run_id=run_id,
        )

        _active_runs[run_id]["status"] = "completed"
        response = format_sync_response(final_state, request, run_id=run_id)
        return JSONResponse(content=response.model_dump(exclude_none=True))

    except WorkflowError as e:
        logger.error(f"OpenAI sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow error: {e}")
    finally:
        _active_runs.pop(run_id, None)


async def _openai_stream(request: ChatCompletionRequest, kwargs: Dict[str, Any]):
    """Handle streaming chat completion.

    #267: Dual-emit — yields OpenAI SSE to the caller AND pushes raw
    LangGraph events to the event bus so headless V.E.G.A.S. can observe.
    """
    try:
        raw_stream = workflow_runner.run_streaming(
            goal=kwargs["goal"],
            text_to_process=kwargs.get("text_to_process"),
            image_to_process=kwargs.get("image_to_process"),
            use_simple_chat=kwargs.get("use_simple_chat", False),
            conversation_id=kwargs.get("conversation_id"),
            prior_messages=kwargs.get("prior_messages"),
        )

        # Tee the raw stream: feed OpenAI translator AND push to event bus
        async def _tee_for_headless(stream):
            bus_run_id = None
            async for event in stream:
                # Capture run_id from the first event that carries it
                if bus_run_id is None and isinstance(event, dict) and "run_id" in event:
                    bus_run_id = event["run_id"]
                if bus_run_id:
                    await _event_bus.push(bus_run_id, event)
                yield event
            # Signal end-of-stream to any headless observers
            if bus_run_id:
                await _event_bus.close(bus_run_id)

        teed_stream = _tee_for_headless(raw_stream)
        translator = OpenAiTranslator(model=request.model)

        async def stream_with_tracking():
            run_id = None
            try:
                async for sse_line in translator.translate(teed_stream):
                    # Capture run_id for active runs tracking
                    if run_id is None and translator.run_id:
                        run_id = translator.run_id
                        _active_runs[run_id] = {"model": request.model, "status": "streaming"}
                    yield sse_line
            finally:
                if run_id:
                    _active_runs.pop(run_id, None)

        return StreamingResponse(
            stream_with_tracking(),
            media_type="text/event-stream",
        )
    except WorkflowError as e:
        logger.error(f"OpenAI streaming error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow streaming error: {e}")


@app.get("/v1/models")
def list_models():
    """
    Returns available LAS routing profiles as OpenAI model objects.

    The model name is a routing profile selector, not an actual LLM model identifier.
    Actual LLM model info is observability data visible via state snapshots.
    """
    profiles = [
        {"id": "las-default", "description": "Full specialist routing (triage → SA → PD → EI)"},
        {"id": "las-simple", "description": "Simple chat mode (single ChatSpecialist)"},
    ]

    return {
        "object": "list",
        "data": [
            {
                "id": p["id"],
                "object": "model",
                "created": 0,
                "owned_by": "las",
            }
            for p in profiles
        ],
    }


@app.get("/v1/runs/active")
def get_active_runs():
    """
    Returns currently active run IDs for observability head discovery.

    This is the glue between the two heads (ADR-UI-003): when a run is initiated
    from an external client (e.g., AnythingLLM via /v1/chat/completions),
    V.E.G.A.S. needs to know the run_id to attach its observability panels.
    """
    return {
        "runs": [
            {"run_id": rid, **info}
            for rid, info in _active_runs.items()
        ]
    }


@app.get("/v1/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    """
    SSE endpoint for headless observation of externally-initiated runs (#267).

    V.E.G.A.S. discovers run IDs via ``GET /v1/runs/active`` then connects
    here to receive AG-UI events in real time.  The raw LangGraph events are
    pushed by ``_openai_stream``'s tee and translated to AG-UI format here.
    """
    if run_id not in _active_runs:
        raise HTTPException(status_code=404, detail="Run not found or already completed")

    queue = await _event_bus.subscribe(run_id)

    async def _generate():
        translator = AgUiTranslator()

        async def _queue_as_stream():
            while True:
                event = await queue.get()
                if event is None:
                    return  # sentinel — stream ended
                yield event

        async for ag_event in translator.translate(_queue_as_stream()):
            yield f"data: {ag_event.model_dump_json()}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


## ---------------------------------------------------------------------------
## Observability Head — existing endpoints (unchanged)
## ---------------------------------------------------------------------------

@app.get("/v1/progress/{run_id}")
async def get_progress(run_id: str):
    """
    Poll for intra-node progress entries during long-running specialist execution.
    Returns accumulated entries since last poll, then clears them.
    UI polls this every 2-3s while a run is active.
    """
    from .utils.progress_store import drain
    entries = drain(run_id)
    return {"entries": entries}


@app.get("/v1/archives/{filename}")
async def download_archive(filename: str):
    """
    Serves archive zip files for download.
    Uses AGENTIC_SCAFFOLD_ARCHIVE_PATH env var (same as ArchiverSpecialist).
    """
    # Security: only allow .zip files and prevent path traversal
    if not filename.endswith(".zip") or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Use same archive path as ArchiverSpecialist for consistency
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
