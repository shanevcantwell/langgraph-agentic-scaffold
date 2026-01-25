# app/src/api.py
# --- Environment Variable Loading ---
# This MUST be the first import and execution, to ensure that all subsequent
# modules have access to the environment variables.
from dotenv import load_dotenv
load_dotenv()
print("Environment variables from .env file loaded.")

from typing import Dict, Optional, Any
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
import gradio as gr
from .workflow.runner import WorkflowRunner
from .utils.errors import WorkflowError
from .utils.cancellation_manager import CancellationManager
from langsmith import Client
from .interface.translator import AgUiTranslator

langsmith_client: Optional[Client] = None
logger = logging.getLogger(__name__)

workflow_runner: WorkflowRunner | None = None

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

                # Check for errors (Task 2.7: error_report moved to scratchpad)
                scratchpad = node_output.get("scratchpad", {})
                error_report = scratchpad.get("error_report", "") if isinstance(scratchpad, dict) else ""
                if "error" in node_output or error_report:
                    error_msg = node_output.get("error", "Unknown error")
                    # Stream error immediately
                    yield f"data: {json.dumps({'error': error_msg, 'error_report': error_report})}\n\n"

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
                        if key in ["messages", "routing_history"]:
                            # operator.add: append to lists
                            accumulated_state.setdefault(key, []).extend(value if isinstance(value, list) else [value])
                        elif key in ["artifacts", "scratchpad"]:
                            # operator.ior: merge dictionaries
                            accumulated_state.setdefault(key, {}).update(value if isinstance(value, dict) else {})
                        else:
                            # No annotation: overwrite with latest value
                            accumulated_state[key] = value

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
        final_state_summary = {
            "routing_history": accumulated_state.get("routing_history", []),
            "turn_count": accumulated_state.get("turn_count", 0),
            "task_is_complete": accumulated_state.get("task_is_complete", False),
            "next_specialist": accumulated_state.get("next_specialist"),
            "recommended_specialists": scratchpad.get("recommended_specialists") if isinstance(scratchpad, dict) else None,
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
        return {"runs": [r.dict() for r in runs]}
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
        "research_orchestrator": "research",
        "browse_specialist": "research",
        "synthesizer_specialist": "research",
        "web_specialist": "research",
        # Chat Subgraph
        "chat_specialist": "chat",
        "progenitor_alpha_specialist": "chat",
        "progenitor_bravo_specialist": "chat",
        "tiered_synthesizer_specialist": "chat",
        "default_responder_specialist": "chat",
        # Data & Analysis
        "data_extractor_specialist": "data",
        "sentiment_classifier_specialist": "data",
        "data_processor_specialist": "data",
        "text_analysis_specialist": "data",
        # File Operations
        "file_operations_specialist": "files",
        "navigator_specialist": "files",
        "batch_processor_specialist": "files",
        # Browser
        "navigator_browser_specialist": "browser",
        # Builders
        "web_builder": "builders",
        "critic_specialist": "builders",
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
    ADR-CORE-018: Resume a workflow from an interrupt point.

    When DialogueSpecialist triggers an interrupt(), this endpoint allows
    the user to provide their clarification and continue the workflow.

    The thread_id must match the one returned in the interrupt payload.
    The user_input will be injected as the return value of interrupt().
    """
    if not workflow_runner:
        raise HTTPException(status_code=503, detail="Workflow runner not initialized")

    logger.info(f"Received resume request for thread_id: {request.thread_id}")

    try:
        result = await workflow_runner.resume(
            thread_id=request.thread_id,
            user_input=request.user_input
        )

        if "error" in result:
            logger.error(f"Resume failed: {result['error']}")
            raise HTTPException(status_code=500, detail=result["error"])

        return {"status": "Workflow resumed successfully", "final_state": result}

    except ValueError as e:
        # Checkpointing not enabled
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
            use_simple_chat=request.use_simple_chat
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
        logger.info(f"Received sync request to invoke graph with prompt: '{request.input_prompt}'")
        final_state = workflow_runner.run(
            goal=request.input_prompt,
            text_to_process=request.text_to_process,
            image_to_process=request.image_to_process,
            use_simple_chat=request.use_simple_chat
        )
    
        # Task 2.7: error_report moved to scratchpad
        scratchpad = final_state.get("scratchpad", {})
        if error_report := (scratchpad.get("error_report") if isinstance(scratchpad, dict) else None):
            logger.error("Workflow ended with an error. Returning error report.")
            return InvokeResponse(final_output={"error_report": error_report})
    
        # The final state from the workflow runner is the complete dictionary we want.
        # We pass it directly as the value for the 'final_output' field in our response model.
        # This ensures the client receives the full state, including 'artifacts', 'messages', etc.
        return InvokeResponse(final_output=final_state)

    except WorkflowError as e:
        logger.error(f"Workflow execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution error: {e}")

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
            use_simple_chat=request.use_simple_chat
        )
        return StreamingResponse(
            _standard_stream_formatter(raw_stream),
            media_type="text/event-stream",
        )
    except WorkflowError as e:
        logger.error(f"Workflow streaming error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow streaming error: {e}")


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
