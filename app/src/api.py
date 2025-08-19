# app/src/api.py
import logging
from logging.handlers import RotatingFileHandler
import pathlib
import os
from dotenv import load_dotenv # <<< 1. IMPORT THE LIBRARY

# --- This is the ONLY place this configuration should happen ---

# 2. LOAD ENVIRONMENT VARIABLES FROM .env FILE
# This should be done before any other code that might need them.
load_dotenv()

# 3. Get the project root directory dynamically
current_file_dir = pathlib.Path(__file__).parent.parent
project_root = current_file_dir.parent
log_file_path = project_root / "logs" / "specialisthub_debug.log"

# 4. Ensure the log directory exists
log_file_path.parent.mkdir(parents=True, exist_ok=True)

# 5. Get log level from environment variable, default to INFO
log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
# Ensure it's a valid level, otherwise default to INFO
log_level = getattr(logging, log_level_str, logging.INFO)


# 6. Configure handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=5)
file_handler.setLevel(logging.DEBUG) # File logs are always detailed
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(log_level) # Console log level is configurable
console_handler.setFormatter(formatter)

# 7. Configure the root logger
# The root logger's level should be the most verbose of its handlers (DEBUG)
# to allow messages to pass through to the handlers for their own filtering.
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[file_handler, console_handler],
    force=True
)

logger = logging.getLogger(__name__)
logger.info(f"Logging configured. Console log level set to {log_level_str}.")

# --- The rest of your api.py file ---
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
    title="SpecialistHub Agentic System API",
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