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
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
import gradio as gr
from .workflow.runner import WorkflowRunner
from .utils.errors import WorkflowError
from langsmith import Client
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
    try:
        # This will respect the environment variables (LANGCHAIN_TRACING_V2, etc.)
        langsmith_client = Client()
        logger.info("--- FastAPI startup: LangSmith client initialized successfully. ---")
    except Exception as e:
        logger.error(f"Failed to initialize LangSmith client on startup: {e}", exc_info=True)
        langsmith_client = None
    
    yield
    
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

class InvokeResponse(BaseModel):
    final_output: Dict[str, Any] = Field(
        ...,
        description="The final output from the graph's END state."
    )

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "API is running"}
async def _stream_formatter(generator):
    """
    This internal generator formats the raw output from the workflow runner
    into the specific JSON structure the Gradio UI expects.
    """
    async for chunk in generator:
        # The raw stream from LangGraph is a dictionary where keys are node names.
        # We can inspect this to provide real-time status updates.
        for node_name, node_output in chunk.items():
            # When a specialist node is invoked, its output is nested under its name.
            # We can use this event to send a status update to the UI.
            if isinstance(node_output, dict) and "messages" in node_output:
                status_update = f"Executing specialist: {node_name}..."
                # Yield a UI-compatible status update
                yield f"data: {json.dumps({'status': status_update})}\n\n"

    # After the main loop, we can yield a final state if needed,
    # but for now, we just signal completion.
    yield f"data: {json.dumps({'status': 'Workflow complete.'})}\n\n"

@app.post("/v1/graph/stream")
async def stream_graph(request: InvokeRequest):
    """Streams the workflow execution step by step."""
    try:
        logger.info(f"Received request to stream graph with prompt: '{request.input_prompt}'")
        raw_stream = workflow_runner.run_streaming(
            goal=request.input_prompt, text_to_process=request.text_to_process, image_to_process=request.image_to_process
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
            goal=request.input_prompt, text_to_process=request.text_to_process, image_to_process=request.image_to_process
        )
    
        if error_report := final_state.get("error_report"):
            logger.error("Workflow ended with an error. Returning error report.")
            return InvokeResponse(final_output={"error_report": error_report})
    
        # The final state from the workflow runner is the complete dictionary we want.
        # We pass it directly as the value for the 'final_output' field in our response model.
        # This ensures the client receives the full state, including 'artifacts', 'messages', etc.
        return InvokeResponse(final_output=final_state)

    except WorkflowError as e:
        logger.error(f"Workflow execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Workflow execution error: {e}")
