# V.E.G.A.S. Terminal — Web UI Architecture

**Purpose:** Technical reference for the V.E.G.A.S. Terminal web UI — layout, data flow, event handling, and observability features.
**Audience:** Developers extending the UI or debugging display issues.
**Updated:** 2026-02-21

---

## Overview

The web UI is a vanilla JS application (no framework) that streams LAS workflow execution in real time. It renders specialist routing, tool calls, reasoning, artifacts, and fork breadcrumbs as they happen.

**Key files:**
| File | Purpose |
|------|---------|
| [app.js](../app/web-ui/public/app.js) | All frontend logic — event handling, rendering, state management |
| [style.css](../app/web-ui/public/style.css) | Themes, layout, component styles |
| [index.html](../app/web-ui/public/index.html) | DOM structure |
| [server.js](../app/web-ui/server.js) | Express proxy — serves static files, proxies `/v1/*` to the Python backend |

---

## Layout

### Left Column (40%)

| Panel | Element | Purpose |
|-------|---------|---------|
| **Command Bar** | `#command-panel` | Prompt input (Shift+Enter multiline), file upload (text/image), simple chat toggle, Execute/Cancel |
| **System Status** | `#status-panel` | Single-line operational status updated in real time |
| **Neural Grid** | `#specialist-panel` | Specialist node visualization — toggleable Grid View (6 nodes) or Graph View (Mermaid flowchart by category) |
| **Routing Log** | `#routing-panel` | Ticker-style execution path — nodes light up as specialists run |

### Right Column (60%)

| Panel | Element | Purpose |
|-------|---------|---------|
| **Thought Stream** | `#thought-stream-panel` | Real-time internal monologue with semantic entry types (see below) |
| **Mission Report** | `.trace-panel` tabs | Consolidated output: Final Response, Artifacts, State (Inspector + Raw JSON) |

---

## Data Flow

```
Python Backend
    │
    ├── SSE Stream: /v1/graph/stream/events
    │   └── AgUiEvent {id, run_id, type, timestamp, source, data}
    │       └── handleStreamEvent() → processEvent switch
    │
    └── Progress Poll: GET /v1/progress/{run_id}  (every 2.5s)
        └── {entries: [{specialist, tool, iteration, ...}]}
            └── renderProgressEntry() → addThoughtStreamEntry()
```

### SSE Event Types

| Event Type | Handler |
|------------|---------|
| `workflow_start` | Initialize UI, log start |
| `status_update` | Update status bar |
| `node_start` / `specialist_start` | Add routing entry, light up Neural Grid node |
| `node_end` / `specialist_end` | Mark complete, extract scratchpad reasoning/decisions, update artifacts |
| `state_snapshot` | Accumulate in Inspector paging, render prompts/trace/scratchpad |
| `log` | Detect MCP call patterns in message text |
| `error` | Log error, render error report |
| `workflow_end` | Stop polling, snapshot to run history, render final report |
| `clarification_required` | Show modal for user input (ADR-CORE-042) |

---

## Thought Stream

The Thought Stream renders semantic entries during workflow execution. Each entry has a type that determines its badge and rendering style.

| Type | Badge | When |
|------|-------|------|
| `routing` | ROUTE | Router decisions, specialist transitions |
| `mcp` | MCP | External tool calls (filesystem, terminal, react_step) |
| `fork` | FORK | fork() invocation — shows child routing path + truncated child_run_id |
| `reasoning` | THINK | Specialist decision logic (collapsible for long text) |
| `artifact` | ARTIFACT | New artifact creation |
| `lifecycle` | SYS/DONE | Start/complete/error lifecycle events |
| `error` | ERROR | Exceptions or failures |
| `success` | OK | Successful completion |

Max entries: 100 (oldest removed on overflow).

---

## Intra-Node Progress

**Problem:** LangGraph's `astream()` yields events per graph node. PD is a single node that runs a react_step loop for up to 50 iterations — potentially 35+ minutes. During this time, the SSE stream is silent.

**Solution:** Progress polling. PD publishes entries to a thread-safe in-memory store (`progress_store.py`) after each tool dispatch. The UI polls `GET /v1/progress/{run_id}` every 2.5 seconds.

### Backend

```python
# progress_store.py — thread-safe publish/drain
publish(run_id, entry)  # Called from PD after each tool call
drain(run_id)           # Called from API endpoint, returns + clears entries

# api.py
@app.get("/v1/progress/{run_id}")
async def get_progress(run_id: str):
    return {"entries": drain(run_id)}
```

### Frontend

```javascript
startProgressPolling(runId)   // Starts 2.5s interval on workflow_start
stopProgressPolling()         // Clears interval on workflow_end

renderProgressEntry(entry)    // Routes to addThoughtStreamEntry by type:
                              //   fork → 'fork' with child route breadcrumb
                              //   _start → 'lifecycle'
                              //   regular → 'mcp' or 'error'
```

### Progress Entry Schema

```json
{
    "specialist": "project_director",
    "iteration": 2,
    "tool": "list_directory",
    "args_summary": "{\"path\": \"/workspace/test\"}",
    "success": true,
    "observation_preview": "[FILE] /workspace/test/1.txt...",
    "fork_metadata": null
}
```

Fork entries include:
```json
{
    "fork_metadata": {
        "child_run_id": "a1b2c3d4-...",
        "child_routing_history": ["triage_architect", "systems_architect", "facilitator", "router", "project_director"],
        "had_error": false
    }
}
```

### Future Upgrade Path

The polling approach is simple and reliable. If latency matters later, the progress store can be consumed from within the SSE stream instead — `_standard_stream_formatter` can check the progress store on timeouts between `astream()` yields. Same publish() calls, different consumer. No specialist code changes needed.

---

## Inspector (State Tab)

The Inspector provides post-execution deep inspection of specialist state snapshots. It's populated from `state_snapshot` SSE events emitted at specialist boundaries.

### Prompt Inspector
- **System Prompt** — collapsible, shows char count
- **Assembled Prompt** — default expanded, shows the full context window the specialist received

### Tool Chain Viewer
For ReAct-enabled specialists (PD, EI, TA), renders `react_trace` as an interactive timeline:

- Iteration number + success/error status
- Tool call name, ID, and arguments (JSON)
- Observation (collapsible for >200 chars)
- **Fork breadcrumb** — CHILD INVOCATION panel with routing path nodes and truncated child_run_id
- Thought (when populated by react_step)

### Scratchpad Viewer
Key-value pairs from specialist scratchpad — long values collapsible, JSON objects prettified.

---

## Fork Observability

Fork breadcrumbs appear in two places:

### Live (Thought Stream)
During PD execution, fork entries appear via progress polling:
- Orange FORK badge
- Specialist name and fork prompt summary
- Child routing path (e.g., `triage_architect → systems_architect → facilitator → router → project_director`)
- Truncated child_run_id for cross-referencing
- Red border for errors

### Post-Hoc (Inspector Tool Chain)
After PD completes, fork entries in the react_trace include a CHILD INVOCATION panel:
- Orange panel with routing path breadcrumb nodes
- Child_run_id for finding the child's archive
- Error flag when the child failed

### Archive Linkage
- **Drill down:** Parent's `react_trace` has `fork_metadata.child_run_id` → find child archive
- **Climb up:** Child's `manifest.json` has `parent_run_id` → find parent archive

---

## Themes

Three themes via CSS custom properties, persisted in localStorage:

| Theme | Description |
|-------|-------------|
| **Mango** (default) | Pumpkin orange on cream |
| **Dark** | Ripe mango on navy |
| **Terminal** | Retro CRT green on black with scanlines |

---

## Context Selection (Run History)

After each workflow completes, the run is saved to `sessionStorage`. The Mission Report supports paging through past runs. Users can check artifacts and final responses to inject as context into the next prompt — sent as `prior_messages` in the workflow payload.

---

## Debugging

### Browser Console

The UI logs diagnostic info for common issues:
```javascript
[workflow_end] Received data: {...}
[workflow_end] Archive exists: true/false
```

### Progress Visibility

If PD appears stuck (no Thought Stream updates), check:
1. Is progress polling active? (`progressInterval` should be set)
2. Is the backend receiving progress? (`docker exec langgraph-app` and check PD logs)
3. Is the proxy routing `/v1/progress/*`? (server.js proxies all `/v1/*`)

### Archive Cross-Reference

The archive is authoritative. If the UI shows something different:
```bash
# Check what actually executed
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check PD's tool history
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.scratchpad.react_trace'

# Find child archives by parent
unzip -p ./logs/archive/run_*.zip manifest.json | jq 'select(.parent_run_id != null)'
```
