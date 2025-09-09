# app/src/api.py
import logging
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from .workflow.runner import WorkflowRunner

# --- MODIFICATION START: Framework-Native Lifecycle Management ---
# Import the LangSmith client and create a global handle for it.
# This handle will be initialized during the FastAPI startup event.
from langsmith import Client
langsmith_client: Optional[Client] = None
# --- MODIFICATION END ---

# --- Application Bootstrap ---
logger = logging.getLogger(__name__)

# --- FastAPI Application ---
app = FastAPI(
    title="Agentic System API",
    description="An API for interacting with the LangGraph-based multi-agent system.",
    version="1.0.0"
)

# --- MODIFICATION START: Framework-Native Lifecycle Management ---
@app.on_event("startup")
def startup_event_handler():
    """
    Initializes the LangSmith client at application startup.
    This ensures a single client instance is used throughout the application's lifecycle.
    """
    global langsmith_client
    try:
        # This will respect the environment variables (LANGCHAIN_TRACING_V2, etc.)
        langsmith_client = Client()
        logger.info("--- FastAPI startup: LangSmith client initialized successfully. ---")
    except Exception as e:
        logger.error(f"Failed to initialize LangSmith client on startup: {e}", exc_info=True)
        langsmith_client = None

@app.on_event("shutdown")
def shutdown_event_handler():
    """
    Handles graceful shutdown by explicitly calling the LangSmith client's
    shutdown method. This is a blocking call that ensures all buffered traces
    are sent before the application exits.
    """
    global langsmith_client
    if langsmith_client:
        try:
            logger.info("--- FastAPI shutdown: Flushing LangSmith traces ---")
            langsmith_client.shutdown()
            logger.info("--- LangSmith trace flush complete ---")
        except Exception as e:
            logger.error(f"Error during LangSmith trace flush on shutdown: {e}", exc_info=True)
# --- MODIFICATION END ---


# --- Data Contracts ---
class InvokeRequest(BaseModel):
    input_prompt: str = Field(
        ...,
        description="The initial user prompt to send to the agentic graph.",
        examples=["What is the capital of France?"]
    )

class InvokeResponse(BaseModel):
    final_output: Dict[str, Any] = Field(
        ...,
        description="The final output from the graph's END state."
    )

workflow_runner = WorkflowRunner()


# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "SpecialistHub API is running"}

@app.post("/v1/graph/invoke", response_model=InvokeResponse)
def invoke_graph(request: InvokeRequest):
    logger.info(f"Received request to invoke graph with prompt: '{request.input_prompt}'")
    final_state = workflow_runner.run(goal=request.input_prompt)

    if error_report := final_state.get("error_report"):
        logger.error("Workflow ended with an error. Returning error report.")
        return InvokeResponse(final_output={"error_report": error_report})

    return InvokeResponse(final_output=final_state)
