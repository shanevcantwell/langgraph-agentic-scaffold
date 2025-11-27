# **UX/UI & API Integration Guide**

# **Version: 4.0**

# **Status: ACTIVE**

This document defines the API contracts and data structures required to build a user interface for the agentic system. It is a technical specification for front-end developers and UI-focused AI agents.

## **1.0 Core Philosophy: Skinning & Theming**

The backend is headless and exposes a consistent data flow via Server-Sent Events (SSE). The front-end's primary role is to provide a "skin" for this flow. This guide enables the creation of diverse themes (e.g., "1970s retro," "cyberpunk terminal," "minimalist clinical," "ADHD-friendly focus mode") by defining the key information that any UI must present to the user.

## **2.0 Conceptual UI Components**

Any user interface for this system is composed of three primary conceptual components that are powered by the backend API.

### **2.1 The Command Bar (User Input)**

The user's entry point for interacting with the agent.

*   **Description:** A text input area where the user types their prompt, with optional file/image upload capabilities and a simple chat mode toggle.
*   **API Interaction:** Submitting a prompt triggers a `POST` request to `/v1/graph/stream` (streaming) or `/v1/graph/invoke` (synchronous).

### **2.2 The Agent Log (Real-time Feedback)**

Provides a live, streaming view of the agent's internal state and actions. This is crucial for user trust and transparency.

*   **Description:** A scrolling log that displays status messages as specialists execute (e.g., "Executing specialist: chat_specialist...").
*   **API Interaction:** The UI consumes the `StreamingResponse` from `/v1/graph/stream` endpoint and displays `status` fields from SSE events.

### **2.3 The Artifact Display (The Result)**

The area where the final output of the agent's work is presented.

*   **Description:** A flexible component that can render different types of final products (HTML, Markdown, images, archive reports).
*   **API Interaction:** Final artifacts are delivered in the last SSE event from `/v1/graph/stream` with keys: `final_state`, `archive`, `html`, `image`.

### **2.4 The Thought Stream (Real-time Observability)**

Provides real-time visibility into the agent's internal reasoning process. This is **observability data only** - it does NOT contribute to the final response synthesis.

*   **Description:** A scrolling log of cognitive events: specialist start/end, reasoning traces, MCP service calls, artifact generation notifications.
*   **Purpose:** User transparency and debugging. Shows "how the agent thinks" without affecting output.
*   **API Interaction:** Consumes AG-UI events from `/v1/graph/stream/events` and extracts observability data from `scratchpad` in `NODE_END` events.

**Key Distinction from Agent Log:**
- **Agent Log**: High-level status messages ("Executing specialist: X...")
- **Thought Stream**: Detailed cognitive traces (reasoning, MCP calls, decisions)

## **3.0 API Endpoints**

### **3.1 `POST /v1/graph/invoke`**

*   **Description:** Synchronous, non-streaming endpoint for automated testing or simple use cases where only the final result is needed.
*   **Request Body:**
    ```json
    {
      "input_prompt": "Your detailed request for the agent goes here.",
      "text_to_process": "(Optional) The content of an uploaded text file.",
      "image_to_process": "(Optional) A base64-encoded string of an uploaded image.",
      "use_simple_chat": false
    }
    ```
*   **Success Response (200 OK):**
    ```json
    {
      "final_output": {
        "messages": [...],
        "artifacts": {...},
        "routing_history": [...],
        "turn_count": 1,
        "task_is_complete": true
      }
    }
    ```

### **3.2 `POST /v1/graph/stream`**

*   **Description:** Primary endpoint for UI interaction. Initiates an agentic workflow and returns real-time Server-Sent Events (SSE).
*   **Request Body:**
    ```json
    {
      "input_prompt": "Your detailed request for the agent goes here.",
      "text_to_process": "(Optional) The content of an uploaded text file.",
      "image_to_process": "(Optional) A base64-encoded string of an uploaded image.",
      "use_simple_chat": false
    }
    ```
*   **Request Fields:**
    - `input_prompt` (required): User's request to the agent
    - `text_to_process` (optional): Content from uploaded text file
    - `image_to_process` (optional): Base64-encoded image string
    - `use_simple_chat` (optional, default: `false`):
      - `false`: Tiered chat mode with parallel progenitors (higher quality, slower)
      - `true`: Simple chat mode with single specialist (faster, single perspective)
*   **Success Response (200 OK):** A `StreamingResponse` with `media_type="text/event-stream"`.
*   **Stream Format:** SSE events with format `data: {JSON}\n\n`

## **4.0 Data Contracts**

### **4.1 Server-Sent Events (SSE) from `/v1/graph/stream`**

The stream sends JSON objects prefixed with `data: `. Each event can contain any combination of these fields:

**Status Update Events (during execution):**
```
data: {"status": "Executing specialist: router_specialist..."}
data: {"status": "Executing specialist: chat_specialist..."}
data: {"status": "Executing specialist: end_specialist..."}
```

These events are sent in real-time as each specialist begins execution. The specialist name follows the pattern `"Executing specialist: <specialist_name>..."`.

**Final Event (workflow complete):**
```
data: {
  "status": "Workflow complete.",
  "final_state": { ... },
  "archive": "# Archive Report\n...",
  "html": "<html>...</html>"
}
```

### **4.1.1 Tracking Active Specialist**

To display the currently-executing specialist in your UI:

```python
import re

async for update in api_client.invoke_agent_streaming(...):
    if "status" in update:
        status_msg = update["status"]

        # Extract specialist name from status message
        match = re.match(r"Executing specialist: (\w+)\.\.\.", status_msg)
        if match:
            current_specialist = match.group(1)
            # Update UI with current specialist name
            display_active_specialist(current_specialist)

        # Check for completion
        if status_msg == "Workflow complete.":
            clear_active_specialist()
```

**Example Stream Sequence (Tiered Chat):**
```
data: {"status": "Executing specialist: router_specialist..."}
data: {"status": "Executing specialist: progenitor_alpha_specialist..."}
data: {"status": "Executing specialist: progenitor_bravo_specialist..."}
data: {"status": "Executing specialist: tiered_synthesizer_specialist..."}
data: {"status": "Executing specialist: end_specialist..."}
data: {"status": "Workflow complete.", "final_state": {...}, "archive": "...", "html": "..."}
```

Note: Parallel specialists (progenitor_alpha/bravo) may appear in either order depending on which completes first.

### **4.1.2 AG-UI Event Schema (`/v1/graph/stream/events`)**

The `/v1/graph/stream/events` endpoint returns structured AG-UI events for rich UI integration:

**Event Structure:**
```json
{
  "type": "node_end",
  "run_id": "abc123",
  "timestamp": "2024-01-15T10:30:00Z",
  "source": "triage_architect",
  "data": {
    "scratchpad": {...},
    "artifacts": {...},
    "status": "Completed triage_architect"
  }
}
```

**Event Types:**
| Type | When Emitted | Data Contents |
|------|--------------|---------------|
| `workflow_start` | Graph execution begins | `run_id` |
| `node_start` | Specialist begins | `status` |
| `status_update` | Progress update | `status` message |
| `log` | Internal log entry | `message` |
| `node_end` | Specialist completes | `scratchpad`, `artifacts`, `status` |
| `error` | Error occurred | `error`, `error_report` |
| `workflow_end` | Graph execution complete | `final_state`, `archive`, `html` |

**Thought Stream Extraction from `node_end` events:**
```javascript
// In handleStreamEvent(event)
if (event.type === 'node_end') {
    const scratchpad = event.data.scratchpad || {};

    // Triage reasoning
    if (scratchpad.triage_reasoning) {
        addThoughtStreamEntry('TRIAGE', scratchpad.triage_reasoning);
    }

    // Facilitator status
    if (scratchpad.facilitator_complete) {
        addThoughtStreamEntry('FACILITATOR', 'Context gathering complete');
    }

    // Router decision
    if (scratchpad.router_decision) {
        addThoughtStreamEntry('ROUTER', scratchpad.router_decision);
    }
}
```

### **4.2 Final State Object**

The `final_state` object in the final SSE event contains:

```json
{
  "routing_history": ["chat_specialist"],
  "turn_count": 1,
  "task_is_complete": true,
  "next_specialist": null,
  "recommended_specialists": null,
  "error_report": null,
  "artifacts": ["response_mode", "final_user_response.md", "archive_report.md"],
  "scratchpad": {"key": "value"},
  "messages_summary": [
    {"type": "human", "content": "User prompt..."},
    {"type": "ai", "content": "Agent response..."}
  ]
}
```

**Field Descriptions:**
- `routing_history`: List of specialists executed in order
- `turn_count`: Number of conversation turns
- `task_is_complete`: Boolean indicating workflow completion
- `next_specialist`: Name of next specialist to execute (null if complete)
- `recommended_specialists`: Router's recommendations (null if not applicable)
- `error_report`: Error message (null if no errors)
- `artifacts`: List of artifact keys available (actual artifact content stored separately)
- `scratchpad`: Transient state data (large items truncated)
- `messages_summary`: Conversation history with message types and content (truncated to 200 chars)

### **4.3 Artifacts Dictionary**

Artifacts are stored as a dictionary with string keys. Common artifact keys:
- `archive_report.md`: Markdown report of workflow completion
- `html_document.html`: Generated HTML content
- `final_user_response.md`: The main response to the user
- `response_mode`: Mode used for response generation (e.g., "tiered_full")
- `alpha_response`, `bravo_response`: Individual progenitor responses (tiered mode)

### **4.4 Observability Scratchpad Keys**

Specialists emit thinking traces to `scratchpad` for UI observability. These are **NOT used for response synthesis** - `EndSpecialist` only reads `user_response_snippets` from scratchpad.

**Convention (Generic Pattern):**
- Keys ending in `_reasoning` or `_decision` are automatically displayed in the Thought Stream
- Example: `triage_reasoning`, `router_decision`, `batch_processor_reasoning`
- The UI extracts the specialist name from the key prefix (e.g., `triage_reasoning` → "TRIAGE")

**Adding Observability to a New Specialist:**
```python
return {
    "scratchpad": {
        "myspecialist_reasoning": "Decided to X because Y..."
    }
}
```
No UI changes required - the generic pattern handles it.

**Reserved Keys (Not Observability):**
| Key | Purpose |
|-----|---------|
| `facilitator_complete` | Boolean flag (special case, shows "Context gathering complete") |
| `user_response_snippets` | **Response synthesis only** - read by EndSpecialist |

## **5.0 Using the ApiClient**

The `ApiClient` class (`app/src/ui/api_client.py`) handles all communication with the backend API. It provides a clean async generator interface for consuming SSE streams.

### **5.1 Basic Usage**

```python
from ui.api_client import ApiClient

# Instantiate the client (connects to localhost:8000 by default)
api_client = ApiClient()

# Call the streaming API
async for update in api_client.invoke_agent_streaming(
    prompt="What is the capital of France?",
    text_file_path=None,
    image_path=None,
    use_simple_chat=False
):
    # Handle different update types
    if "status" in update:
        print(f"Status: {update['status']}")
    if "final_state" in update:
        print(f"Final state: {update['final_state']}")
    if "archive" in update:
        print(f"Archive report: {update['archive']}")
    if "html" in update:
        print(f"HTML content: {update['html']}")
```

### **5.2 ApiClient Methods**

**`invoke_agent_streaming(prompt, text_file_path, image_path, use_simple_chat)`**
- **Returns:** Async generator yielding dictionaries with keys: `status`, `logs`, `final_state`, `html`, `image`, `archive`
- **Parameters:**
  - `prompt` (str): User's request
  - `text_file_path` (str|None): Path to text file or Gradio File object
  - `image_path` (str|None): Path to image file or Gradio Image object
  - `use_simple_chat` (bool): Toggle between tiered and simple chat modes
- **Timeout:** 300 seconds (5 minutes)

**`_encode_image_to_base64(image_path)`**
- Internal helper method for encoding images
- Automatically called by `invoke_agent_streaming`

### **5.3 Error Handling**

The ApiClient handles errors gracefully and yields them as update dictionaries:

```python
async for update in api_client.invoke_agent_streaming(...):
    if "status" in update and "Error" in update["status"]:
        # Handle error (file read error, API error, etc.)
        print(f"Error occurred: {update['status']}")
        if "logs" in update:
            print(f"Error logs: {update['logs']}")
```

### **5.4 Integration with Gradio**

Example handler function for Gradio components:

```python
import re

async def handle_submit(prompt: str, text_file, image_file, use_simple_chat: bool):
    """Generator function to handle streaming UI updates."""
    async for update in api_client.invoke_agent_streaming(
        prompt, text_file, image_file, use_simple_chat
    ):
        ui_update = {}

        if "status" in update:
            status_msg = update["status"]
            ui_update[status_output] = status_msg

            # Extract and highlight currently-executing specialist
            match = re.match(r"Executing specialist: (\w+)\.\.\.", status_msg)
            if match:
                specialist_name = match.group(1)
                ui_update[active_specialist_output] = f"⚙️ {specialist_name}"

            # Clear specialist indicator on completion
            if status_msg == "Workflow complete.":
                ui_update[active_specialist_output] = "✅ Complete"

        if "logs" in update:
            ui_update[log_output] = update["logs"]
        if "final_state" in update:
            ui_update[json_output] = update["final_state"]
        if "html" in update:
            ui_update[html_output] = update["html"]
        if "archive" in update:
            ui_update[archive_output] = update["archive"]

        if ui_update:
            yield ui_update
```

**Key Points:**
- Status messages update in real-time as each specialist executes
- Use regex to extract specialist name from status for visual indicators
- Final event contains all artifacts and complete state
- Gradio components update reactively as dictionary is yielded

See `app/src/ui/gradio_app.py` for a complete working implementation.

## **6.0 Quick Reference**

### **Minimal UI Requirements**

Any UI must handle these core data flows:

1. **Input** → Send POST to `/v1/graph/stream` with `input_prompt` (required) and optional `text_to_process`, `image_to_process`, `use_simple_chat`
2. **Streaming** → Parse SSE events (`data: {...}`) and extract `status`, `final_state`, `archive`, `html`, `image`
3. **Real-time Tracking** → Parse status messages (`"Executing specialist: <name>..."`) to show active specialist
4. **Display** → Show status updates during execution, final state/artifacts on completion

### **Key Files**

- **API Implementation:** `app/src/api.py` - FastAPI endpoints and SSE formatting
- **AG-UI Translator:** `app/src/interface/translator.py` - Converts LangGraph chunks to AG-UI events
- **API Client:** `app/src/ui/api_client.py` - Python client for SSE consumption
- **Reference UIs:**
  - `app/src/ui/gradio_lassi.py` - Gradio-based L.A.S.S.I. UI
  - `app/web-ui/` - Node.js V.E.G.A.S. Terminal with Thought Stream
- **State Schema:** `app/src/graph/state.py` - GraphState TypedDict definition

### **Testing Endpoints**

```bash
# Test root endpoint
curl http://localhost:8000/

# Test synchronous invoke
curl -X POST http://localhost:8000/v1/graph/invoke \
  -H "Content-Type: application/json" \
  -d '{"input_prompt": "Hello", "use_simple_chat": true}'

# Test streaming (requires SSE client)
curl -X POST http://localhost:8000/v1/graph/stream \
  -H "Content-Type: application/json" \
  -d '{"input_prompt": "Hello", "use_simple_chat": true}'
```

### **Common Gotchas**

- **Async Required:** ApiClient uses `async for` - must be called from async context
- **File Objects:** ApiClient accepts both file paths (str) and Gradio file objects with `.name` attribute
- **Timeout:** Default 300s timeout may need adjustment for long-running workflows
- **SSE Format:** Events are `data: {JSON}\n\n` - must strip `data: ` prefix before parsing
- **Image Encoding:** Images must be base64-encoded strings, not raw bytes
- **Status Pattern:** Specialist status follows exact format `"Executing specialist: <name>..."` - use regex `r"Executing specialist: (\w+)\.\.\."` to extract name
- **Parallel Execution:** In tiered mode, progenitor specialists execute in parallel - status events may arrive in any order