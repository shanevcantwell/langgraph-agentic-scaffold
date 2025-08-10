# app/api.py
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import List, Dict, Any

# --- 1. Define your Data Contracts (The "XSD" part) ---
# Pydantic models define the shape and types of your API data.

class InvokeRequest(BaseModel):
    """The JSON payload the client will send to start a task."""
    input_prompt: str = Field(
        ...,  # This means the field is required
        description="The initial user prompt to send to the agentic graph.",
        examples=["What is the capital of France?"]
    )
    # You could add other fields here later, like session_id, etc.

class InvokeResponse(BaseModel):
    """The final JSON response the server will send back."""
    final_output: Dict[str, Any] = Field(
        ...,
        description="The final output from the graph's END state."
    )
    # You could add other metadata here, like total_cost, tokens_used, etc.


# --- 2. Instantiate the FastAPI Application ---
app = FastAPI(
    title="SpecialistHub Agentic System API",
    description="An API for interacting with the LangGraph-based multi-agent system.",
    version="1.0.0"
)

# TODO: Import and instantiate your LangGraph app from main.py
# from src.main import app as langgraph_app


# --- 3. Define your API Endpoints (The "RPC" part) ---
# These are the functions that will be called by clients.

@app.get("/")
def read_root():
    """A simple health-check endpoint."""
    return {"status": "SpecialistHub API is running"}

@app.post("/v1/graph/invoke", response_model=InvokeResponse)
def invoke_graph(request: InvokeRequest):
    """
    Receives a user prompt, invokes the agentic graph synchronously,
    and returns the final result.
    """
    print(f"Received request to invoke graph with prompt: {request.input_prompt}")

    # This is where you will call your actual LangGraph application
    # For now, we'll use a mock response.
    #
    # inputs = {"messages": [("user", request.input_prompt)]}
    # final_state = langgraph_app.invoke(inputs)
    #
    # return {"final_output": final_state}

    # Mock response for demonstration:
    mock_final_output = {
        "messages": [
            {"type": "human", "content": request.input_prompt},
            {"type": "ai", "content": f"This is a mock response for: '{request.input_prompt}'"}
        ]
    }
    return {"final_output": mock_final_output}

