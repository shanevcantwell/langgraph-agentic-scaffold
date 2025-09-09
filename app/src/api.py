# app/src/api.py
import logging
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any
from .workflow.runner import WorkflowRunner

# --- Application Bootstrap ---
logger = logging.getLogger(__name__)

# --- ARCHITECTURAL MODIFICATION: Explicit Client Lifecycle Management ---
_langsmith_client = None
try:
    from langsmith import Client
    _langsmith_client = Client()
    print("✅ LangSmith client initialized for graceful shutdown.")
except ImportError:
    print("⚠️ LangSmith SDK not found. Graceful shutdown hook is disabled.")
# --- End of Modification ---


# --- FastAPI Application ---
app = FastAPI(...)

@app.on_event("shutdown")
def shutdown_event_handler():
    logger.info("--- FastAPI shutdown event triggered. ---")
    if _langsmith_client:
        try:
            logger.info("Attempting to shut down LangSmith client...")
            # The shutdown method is designed to block until the background
            # thread has finished uploading all buffered traces.
            _langsmith_client.shutdown()
            logger.info("LangSmith client shutdown complete.")
        except Exception as e:
            logger.error(f"Error during LangSmith client shutdown: {e}", exc_info=True)
    else:
        logger.info("No LangSmith client found. Skipping shutdown.")

# --- Data Contracts & Workflow ---
class InvokeRequest(BaseModel):
    input_prompt: str = Field(...)

class InvokeResponse(BaseModel):
    final_output: Dict[str, Any] = Field(...)

workflow_runner = WorkflowRunner()

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
