# app/src/api.py
import logging
import os
from logging.handlers import RotatingFileHandler

# --- Logging Configuration ---
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
log_dir = "logs"
log_file = os.path.join(log_dir, "agentic_server.log")

# Create log directory if it doesn't exist
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure root logger
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        # The application is responsible for its own logging, including rotation.
        RotatingFileHandler(log_file, maxBytes=10485760, backupCount=5), # 10MB per file, 5 backups
        logging.StreamHandler() # Also log to console for real-time feedback.
    ],
    force=True # This will remove any existing handlers, preventing duplicate logs.
)

logger = logging.getLogger(__name__)

from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Dict, Any
from .workflow.runner import WorkflowRunner


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
    return InvokeResponse(final_output=final_state)
