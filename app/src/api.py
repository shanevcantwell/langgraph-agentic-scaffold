# app/src/api.py
import logging
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any
from .workflow.runner import WorkflowRunner

# --- Application Bootstrap ---
# Environment variables are now loaded by the startup script (e.g., server.py)
# that launches this application. This ensures the environment is configured
# before the application code is even imported, making the setup more robust.


# The application is no longer responsible for configuring logging.
# It simply requests a logger instance to use. The server process (Uvicorn)
# will handle the configuration from an external file.
# Note: this is the single source of truth for how to handle logging in this file.
logger = logging.getLogger(__name__)


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


# --- FastAPI Application ---
app = FastAPI(
    title="Agentic System API",
    description="An API for interacting with the LangGraph-based multi-agent system.",
    version="1.0.0"
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

    # Check if a detailed error report was generated. If so, prioritize it.
    if error_report := final_state.get("error_report"):
        logger.error("Workflow ended with an error. Returning error report.")
        return InvokeResponse(final_output={"error_report": error_report})

    return InvokeResponse(final_output=final_state)
