# LAS API Reference

REST API for the LAS multi-agent orchestration system.

Base URL: `http://localhost:8000` (configurable)

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
    {"key": "lmstudio_local", "type": "lmstudio", "model": "llama-3.1", "is_default": false}
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
  "default_llm_config": "lmstudio_local"
}
```

**Response:**
```json
{
  "status": "Configuration updated and workflow reloaded",
  "overrides": {"default_llm_config": "lmstudio_local"}
}
```

---

## Observability Endpoints

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
