# app/src/api.py
import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional
from .workflow.runner import WorkflowRunner
from .utils.errors import WorkflowError
from langsmith import Client
langsmith_client: Optional[Client] = None
logger = logging.getLogger(__name__)

workflow_runner: Optional[WorkflowRunner] = None

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
        logger.info("--- FastAPI shutdown: Allowing time for LangSmith trace flush... ---")
        time.sleep(2) # A 2-second delay is generally sufficient.
        logger.info("--- LangSmith grace period complete. ---")

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

@app.post("/v1/graph/stream")
async def stream_graph(request: InvokeRequest):
    """Streams the workflow execution step by step."""
    try:
        logger.info(f"Received request to stream graph with prompt: '{request.input_prompt}'")
        return StreamingResponse(
            workflow_runner.run_streaming(
                goal=request.input_prompt, text_to_process=request.text_to_process, image_to_process=request.image_to_process
            ),
            media_type="text/event-stream"
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
