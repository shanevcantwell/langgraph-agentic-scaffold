# LAS API Reference

REST API for the LAS multi-agent orchestration system.

Base URL: `http://localhost:8000` (configurable)

---

## Architecture

The API has two independently-developed layers (ADR-UI-003):

| Layer | Module | Endpoints | Purpose |
|-------|--------|-----------|---------|
| **Chat** | `app/src/api.py` | `/v1/graph/*`, `/v1/chat/*`, `/v1/models`, `/v1/system/*` | Workflow execution, OpenAI compatibility |
| **Observability** | `app/src/observability/router.py` | `/v1/runs/*`, `/v1/progress/*`, `/v1/traces/*`, `/v1/graph/topology`, `/v1/archives/*` | Monitoring, traces, archives |

The observability layer is mounted as a FastAPI `APIRouter` — same process, clean module boundary. The **event bus** (`observability/event_bus.py`) and **active runs registry** (`observability/active_runs.py`) are the contract surface: chat heads push events, observability reads them.

---

## Core Endpoints

### POST /v1/graph/stream

**Primary endpoint.** Streams workflow execution via Server-Sent Events (SSE).

**Request:**
```json
{
  "input_prompt": "What is the capital of France?",
  "text_to_process": null,
  "image_to_process": null,
  "use_simple_chat": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `input_prompt` | string | Required. User prompt to process |
| `text_to_process` | string | Optional. Uploaded document content |
| `image_to_process` | string | Optional. Base64-encoded image |
| `use_simple_chat` | boolean | If true, use single ChatSpecialist; if false, use tiered chat (parallel progenitors) |

**Response:** SSE stream with events:

```
data: {"run_id": "abc123"}

data: {"status": "Executing specialist: triage_architect...", "logs": "Entering node: triage_architect"}

data: {"status": "Executing specialist: router_specialist...", "logs": "Entering node: router_specialist"}

data: {"status": "Workflow complete.", "final_state": {...}, "archive": "...", "html": "..."}
```

**Event Types:**

| Event | Description |
|-------|-------------|
| `run_id` | First event. LangSmith trace ID for this run |
| `status` | Specialist execution update. Format: `Executing specialist: <name>...` |
| `logs` | Node entry log. Format: `Entering node: <name>` |
| `error` | Error during execution |
| `error_report` | Detailed error report from scratchpad |
| `final_state` | Terminal event with workflow results |

**Final State Structure:**
```json
{
  "routing_history": ["triage_architect", "router_specialist", "chat_specialist", "end_specialist"],
  "turn_count": 4,
  "task_is_complete": true,
  "next_specialist": null,
  "recommended_specialists": null,
  "error_report": null,
  "artifacts": ["archive_report.md"],
  "scratchpad": {},
  "messages_summary": [
    {"type": "human", "content": "What is the capital of France?"},
    {"type": "ai", "content": "The capital of France is Paris."}
  ]
}
```

---

### POST /v1/graph/invoke

**Synchronous invocation.** Returns full result after workflow completes.

**Request:** Same as `/v1/graph/stream`

**Response:**
```json
{
  "final_output": {
    "messages": [...],
    "artifacts": {...},
    "routing_history": [...],
    "turn_count": 4,
    "task_is_complete": true
  }
}
```

---

### POST /v1/graph/stream/events

**Standardized AG-UI event stream.** Same as `/stream` but uses AG-UI event schema.

**Request:** Same as `/v1/graph/stream`

**Response:** SSE with `AgUiEvent` Pydantic models (JSON serialized).

---

## OpenAI-Compatible Endpoints (ADR-UI-002)

### POST /v1/chat/completions

**OpenAI-compatible chat endpoint.** Supports streaming and sync. Produces spec-compliant responses with no vendor extensions.

The `model` field is a routing profile selector, not an LLM model identifier.

**Request:**
```json
{
  "model": "las-default",
  "messages": [{"role": "user", "content": "Analyze this codebase"}],
  "stream": true
}
```

| Model | Behavior |
|-------|----------|
| `las-default` | Full specialist routing (triage → SA → PD → EI) |
| `las-simple` | Simple chat mode (single ChatSpecialist) |

**Streaming response:** Standard OpenAI SSE format:
```
data: {"id":"chatcmpl-...","choices":[{"delta":{"content":"..."}}]}
data: [DONE]
```

**Sync response:** Standard `ChatCompletion` object.

**Dual-emit (#267):** When streaming, raw LangGraph events are also pushed to the event bus so headless V.E.G.A.S. can observe the run via `GET /v1/runs/{run_id}/events`.

---

### GET /v1/models

**List available routing profiles as OpenAI model objects.**

**Response:**
```json
{
  "object": "list",
  "data": [
    {"id": "las-default", "object": "model", "created": 0, "owned_by": "las"},
    {"id": "las-simple", "object": "model", "created": 0, "owned_by": "las"}
  ]
}
```

---

## Control Endpoints

### POST /v1/graph/cancel/{run_id}

**Cancel running workflow.**

**Response:**
```json
{"status": "Cancellation requested"}
```

---

### POST /v1/graph/resume

**Resume interrupted workflow.** (ADR-CORE-018)

**Request:**
```json
{
  "thread_id": "abc123",
  "user_input": "User's clarification response"
}
```

**Response:**
```json
{
  "status": "Workflow resumed successfully",
  "final_state": {...}
}
```

---

## System Endpoints

### GET /

**Health check.**

**Response:**
```json
{"status": "API is running"}
```

---

### GET /v1/system/llm-providers

**List available LLM providers.**

**Response:**
```json
{
  "providers": [
    {"key": "gemini_pro", "type": "gemini", "model": "gemini-1.5-pro", "is_default": true},
    {"key": "local_default", "type": "local", "model": "llama-3.1", "is_default": false}
  ],
  "current_default": "gemini_pro"
}
```

---

### POST /v1/system/config

**Update runtime configuration.**

**Request:**
```json
{
  "default_llm_config": "local_default"
}
```

**Response:**
```json
{
  "status": "Configuration updated and workflow reloaded",
  "overrides": {"default_llm_config": "local_default"}
}
```

---

## Observability Endpoints

All observability endpoints are served by `app/src/observability/router.py` (mounted as a FastAPI APIRouter). They can be developed and tested independently of the chat layer.

### GET /v1/runs/active

**Discover active run IDs.** V.E.G.A.S. polls this to find externally-initiated runs (e.g., from AnythingLLM via `/v1/chat/completions`).

**Response:**
```json
{
  "runs": [
    {"run_id": "abc123", "model": "las-default", "status": "streaming"}
  ]
}
```

---

### GET /v1/runs/{run_id}/events

**SSE stream for headless observation (#267).** Receives AG-UI events in real time for an active run. Raw LangGraph events are pushed by the chat head's tee and translated to AG-UI format.

**Response:** SSE with `AgUiEvent` Pydantic models (JSON serialized). Sentinel `None` signals end-of-stream.

---

### GET /v1/progress/{run_id}

**Poll intra-node progress entries.** Returns accumulated entries since last poll, then clears them. UI polls every 2-3s while a run is active.

**Response:**
```json
{
  "entries": [
    {"specialist": "project_director", "iteration": 2, "tool": "list_directory", "success": true}
  ]
}
```

---

### GET /v1/traces/{run_id}

**Fetch LangSmith trace tree.**

**Response:**
```json
{
  "runs": [
    {"id": "...", "name": "triage_architect", "start_time": "...", "end_time": "..."},
    {"id": "...", "name": "router_specialist", "start_time": "...", "end_time": "..."}
  ]
}
```

---

### GET /v1/graph/topology

**Graph structure for Neural Grid visualization.** Returns nodes (specialists), edges (routing relationships), and subgraph clustering info.

**Response:**
```json
{
  "nodes": [{"id": "router_specialist", "type": "router", "category": "orchestration", ...}],
  "edges": [{"source": "router_specialist", "target": "project_director", "type": "conditional"}],
  "subgraphs": [{"name": "ChatSubgraph", "managed_specialists": [...]}],
  "entry_point": "triage_architect"
}
```

---

### GET /v1/archives/{filename}

**Download archive zip file.**

**Response:** Binary zip file (`application/zip`)

---

## SSE Parsing Example

```python
import httpx
import json

def stream_workflow(prompt: str):
    """Stream workflow execution and parse SSE events."""
    with httpx.stream(
        "POST",
        "http://localhost:8000/v1/graph/stream",
        json={"input_prompt": prompt}
    ) as response:
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue

            data = json.loads(line[5:].strip())

            if "run_id" in data:
                print(f"Run ID: {data['run_id']}")

            if "status" in data:
                print(f"Status: {data['status']}")

            if "final_state" in data:
                print(f"Done. History: {data['final_state']['routing_history']}")
                return data['final_state']
```

---

## Error Handling

All errors return appropriate HTTP status codes:

| Code | Meaning |
|------|---------|
| 200 | Success (streaming started or completed) |
| 400 | Bad request (invalid parameters) |
| 422 | Validation error (Pydantic) |
| 500 | Internal error (workflow failure) |
| 503 | Service unavailable (runner not initialized) |

Errors during streaming are emitted as SSE events:
```
data: {"error": "Error message", "error_report": "Detailed report..."}
```

---

## Testing

Flow tests use this API with zero mocks. See:
- [app/tests/integration/test_flows.py](../app/tests/integration/test_flows.py) - Flow validation tests
- [app/tests/integration/test_api_streaming_integration.py](../app/tests/integration/test_api_streaming_integration.py) - Streaming tests
