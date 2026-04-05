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
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
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
from .observability import (
    event_bus, active_runs, observability_router, init_observability,
)

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

    # Initialize observability layer with runtime dependencies
    init_observability(
        workflow_runner=workflow_runner,
        langsmith_client=langsmith_client,
    )

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

# Mount observability router (all /v1/runs/*, /v1/progress/*, /v1/traces/*,
# /v1/graph/topology, /v1/archives/* endpoints)
app.include_router(observability_router)

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

@app.post("/v1/graph/cancel/{run_id}")
async def cancel_run(run_id: str):
    """
    Requests cancellation of a running workflow.
    """
    logger.info(f"Received cancellation request for run_id: {run_id}")
    CancellationManager.request_cancellation(run_id)
    return {"status": "Cancellation requested"}


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
        active_runs.register(run_id, {"model": request.model, "status": "running"})

        final_state = workflow_runner.run(
            goal=kwargs["goal"],
            text_to_process=kwargs.get("text_to_process"),
            image_to_process=kwargs.get("image_to_process"),
            use_simple_chat=kwargs.get("use_simple_chat", False),
            run_id=run_id,
        )

        active_runs.update(run_id, status="completed")
        response = format_sync_response(final_state, request, run_id=run_id)
        return JSONResponse(content=response.model_dump(exclude_none=True))

    except WorkflowError as e:
        logger.error(f"OpenAI sync error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow error: {e}")
    finally:
        active_runs.deregister(run_id)


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
                    await event_bus.push(bus_run_id, event)
                yield event
            # Signal end-of-stream to any headless observers
            if bus_run_id:
                await event_bus.close(bus_run_id)

        teed_stream = _tee_for_headless(raw_stream)
        translator = OpenAiTranslator(model=request.model)

        async def stream_with_tracking():
            run_id = None
            try:
                async for sse_line in translator.translate(teed_stream):
                    # Capture run_id for active runs tracking
                    if run_id is None and translator.run_id:
                        run_id = translator.run_id
                        active_runs.register(run_id, {"model": request.model, "status": "streaming"})
                    yield sse_line
            finally:
                if run_id:
                    active_runs.deregister(run_id)

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


