# app/src/api.py
import logging
from logging.handlers import RotatingFileHandler
import pathlib
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

# 5. Configure the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)

if root_logger.handlers:
    for handler in root_logger.handlers:
        root_logger.removeHandler(handler)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

file_handler = RotatingFileHandler(log_file_path, maxBytes=1024*1024*5, backupCount=5)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)

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