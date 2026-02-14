# Facilitator Briefing: How Context Gathering Works in LAS

**Purpose:** Technical briefing on the Facilitator specialist's role in the LAS execution flow.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-12 (context_plan artifact eliminated — reads triage_actions from scratchpad)

---

## Executive Summary

The **Facilitator** is a deterministic, non-LLM specialist that bridges intent classification (Triage) and task execution (Router). Its job is to **autonomously gather background context** before the system decides how to handle a user request, and to **curate retry context** when Exit Interview sends a task back for another attempt.

Key characteristics:
- **Procedural, not LLM-based** — executes a plan, doesn't reason
- **MCP orchestrator** — calls internal and external services via Model Context Protocol
- **Sole context writer** — specialists receive context via `gathered_context`, never accumulate their own (#170)
- **Fresh rebuild each invocation** — no accumulation across retries (#170)
- **Trace knowledge extraction** — surfaces prior write operations on retry (#170)

---

## Where Facilitator Fits in the Execution Flow

### First Pass (New Request)

```
User Request
    |
TriageArchitect (LLM: classifies intent, writes triage_actions to scratchpad)
    |
    [Does scratchpad have triage_actions?]
    |-- YES (context actions) --> Facilitator --> Router --> Specialist
    |-- YES (ask_user only)  --> EndSpecialist (reject with cause, #179)
    '-- NO                   --> Router (direct)
```

### Retry Path (EI says INCOMPLETE)

```
Specialist (e.g., PD)
    |
classify_interrupt --> ExitInterview
    |
    [is_complete?]
    |-- YES --> END
    '-- NO  --> Facilitator (rebuild context + trace knowledge) --> Router --> Specialist
```

### BENIGN Continuation (max_iterations hit, model was working)

```
Specialist hits max_iterations
    |
    [max_iterations_exceeded + (no EI or EI=INCOMPLETE)]
    |
Facilitator: early return, clear flag, don't rebuild context
    |
Router --> Specialist continues
```

### Routing Decision Logic

The routing decision is made in `check_triage_outcome()` ([graph_orchestrator.py](../app/src/workflow/graph_orchestrator.py)):

```python
def check_triage_outcome(self, state: GraphState) -> str:
    triage_actions = state.get("scratchpad", {}).get("triage_actions", [])
    if triage_actions:
        ask_user_count = sum(1 for a in triage_actions if a.get("type") == "ask_user")
        other_count = len(triage_actions) - ask_user_count
        if other_count == 0 and ask_user_count > 0:
            return CoreSpecialist.END.value   # Reject with cause (#179)
        return "facilitator_specialist"
    return CoreSpecialist.ROUTER.value
```

---

## What the Facilitator Actually Does

### Input: Triage Actions from Scratchpad

TriageArchitect writes context-gathering actions to `scratchpad["triage_actions"]`:

```python
# Facilitator reads actions from scratchpad (not artifacts)
triage_actions_data = state.get("scratchpad", {}).get("triage_actions", [])

# Each action dict is parsed into a ContextAction for type-safe dispatch
from app.src.interface.context_schema import ContextAction

class ContextAction(BaseModel):
    type: ContextActionType   # RESEARCH | READ_FILE | SUMMARIZE | LIST_DIRECTORY | ASK_USER
    target: str               # Query, file path, or text
    description: str          # Why this action is needed
    strategy: Optional[str]   # Provider hint (e.g., "google", "duckduckgo")
```

### Context Assembly Order (#170)

Each invocation rebuilds `gathered_context` from scratch. The assembly order is:

1. **Task Strategy** — `task_plan.plan_summary` from SA (switched from Triage reasoning — SA reasons about the full request, Triage's reasoning only explains context-gathering choices)
2. **EI Retry Feedback** — curated `missing_elements` + `reasoning` (only on retry, #167)
3. **Prior Work Knowledge** — extracted write operations from `resume_trace` (only on retry, #170)
4. **WIP Summary** — work-in-progress for BENIGN interrupts (only when `max_iterations_exceeded` without EI, #108)
5. **Plan Action Results** — RESEARCH, READ_FILE, SUMMARIZE, LIST_DIRECTORY, ASK_USER

### Action-by-Action Processing

| Action Type | MCP Service Called | Result |
|-------------|-------------------|--------|
| `RESEARCH` | Internal: `web_specialist.search(query)` | Web search results formatted as markdown links |
| `READ_FILE` | External: `filesystem.read_file(path)` | File contents in code block |
| `SUMMARIZE` | Internal: `summarizer_specialist.summarize(text)` | Condensed summary |
| `LIST_DIRECTORY` | External: `filesystem.list_directory(path)` | Markdown bullet list with full paths |
| `ASK_USER` | LangGraph `interrupt()` | Pauses graph for user input, adds response to context |

**SUMMARIZE file path heuristic:** If the target looks like a file path (starts with `/` or `./`), Facilitator attempts to read the file first via filesystem MCP, then summarizes the content.

**ASK_USER:** Uses LangGraph's `interrupt()` primitive to pause execution. The user's answer is added to `gathered_context` as `### User Clarification`.

**LIST_DIRECTORY path enrichment:** Each entry includes the full path (e.g., `- [FILE] /workspace/test/1.txt`) so downstream specialists have unambiguous paths.

### Output: gathered_context Artifact

```python
{
    "artifacts": {
        "gathered_context": """### Task Strategy
User wants files sorted by content into category subfolders

### Retry Context (from Exit Interview evaluation)
**What still needs to be done:** 4 files still need moving
**Why incomplete:** Only 2 of 6 files were categorized

### Prior Work Completed
- Created directory /workspace/animals
- Moved /workspace/1.txt -> /workspace/animals/1.txt
- Moved /workspace/4.txt -> /workspace/animals/4.txt

### Directory: /workspace
- [FILE] /workspace/2.txt
- [FILE] /workspace/3.txt
- [DIR] /workspace/animals"""
    },
    "scratchpad": {
        "facilitator_complete": True
    }
}
```

---

## #170: Fresh Rebuild (No Accumulation)

### The Problem

Before #170, Facilitator accumulated context: `existing_context + "\n\n---\n\n" + new_context`. On retry, identical Task Strategy + EI Feedback blocks got tripled. PD saw the same instructions 3 times and got confused.

### The Fix

Each invocation rebuilds `gathered_context` from scratch using current plan actions and current state. No reading of prior `gathered_context` from artifacts.

### Trace Knowledge Extraction

On retry (EI said INCOMPLETE), Facilitator reads `resume_trace` from artifacts and extracts a knowledge summary of **write operations only** (create_directory, move_file, write_file). Read operations are omitted because they're cheap to redo and re-reading ensures the model sees current filesystem state.

```python
def _extract_trace_knowledge(self, artifacts: dict) -> Optional[str]:
    trace = artifacts.get("resume_trace", [])
    # Only successful write operations
    # Returns: "### Prior Work Completed\n- Created directory ...\n- Moved ..."
```

### Why Not Pass the Full Trace?

PD starts with `trace = []` each invocation (#170 Step 3). The model gets a fresh start but knows what write operations already succeeded via `gathered_context`. This avoids the stale-trace problem where the model re-feeds its prior conversation and thinks it already finished.

---

## BENIGN Continuation (#114)

When `max_iterations_exceeded` is True, the model was working correctly but ran out of runway. Facilitator detects this and **early returns** without rebuilding context:

```python
if is_benign_continuation:
    return {
        "artifacts": {
            "resume_trace": resume_trace,          # Already in artifacts from PD
            "max_iterations_exceeded": False,       # Clear the flag
        },
        "scratchpad": {"facilitator_complete": True}
    }
```

Two scenarios qualify as BENIGN:
1. **Pure BENIGN:** `max_exceeded` + no EI result (interrupted before EI ran)
2. **BENIGN after EI:** `max_exceeded` + EI said INCOMPLETE (model was working, EI judged)

---

## MCP Integration Details

### Internal MCP (Python services in-process)

Called via `self.mcp_client.call()`:

```python
results = self.mcp_client.call(
    service_name="web_specialist",
    function_name="search",
    query="quantum computing 2026"
)
```

### External MCP (Containerized services via stdio)

Called via the sync-to-async bridge `sync_call_external_mcp()`, with results parsed by `extract_text_from_mcp_result()`:

```python
content = sync_call_external_mcp(
    self.external_mcp_client,
    "filesystem",
    "read_file",
    {"path": "/workspace/config.yaml"}
)
```

The sync bridge handles the async-to-sync translation:
- Facilitator code is synchronous (LangGraph node execution)
- External MCP uses async stdio transport
- `asyncio.run_coroutine_threadsafe()` schedules calls on the main event loop

### Special Case: In-Memory Artifacts

Before calling filesystem MCP, Facilitator checks if the target exists as an in-memory artifact (e.g., uploaded images stored as base64):

```python
if artifact_key in artifacts:
    content = artifacts[artifact_key]  # Use in-memory version
else:
    content = self._read_file_via_filesystem_mcp(target_path)  # Filesystem
```

---

## Error Handling and Graceful Degradation

### Service Unavailability

If external filesystem MCP is not connected:

```python
def _read_file_via_filesystem_mcp(self, path: str) -> Optional[str]:
    if not self._is_filesystem_available():
        return None  # Graceful fail
```

The gathered_context will include: `### File: /path\n[Filesystem service unavailable]`

### Action Execution Failures

Individual action failures don't halt the entire plan:

```python
try:
    # Execute action...
except Exception as e:
    gathered_context.append(f"### Error: {action.target}\nFailed to execute: {e}")
    # Continue with next action
```

---

## What the Facilitator Does NOT Do

| Capability | Facilitator | Who Does It |
|------------|-------------|-------------|
| LLM reasoning | No | TriageArchitect, Router, Specialists |
| Routing decisions | No | Router |
| Task completion loops | No | Graph: EI -> Facilitator -> Router -> PD |
| Direct GraphState mutation | No | SafeExecutor/NodeExecutor |
| Accumulate private context | No (#170) | Specialists produce artifacts; Facilitator curates |
| Relay resume_trace | No (#170) | PD writes resume_trace directly via ior merge |

---

## Archive Forensics

Every workflow run produces an archive at `./logs/archive/run_YYYYMMDD_HHMMSS_<hash>.zip`.

To verify Facilitator execution:

```bash
# Check routing history
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check gathered_context in final state
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.gathered_context'
```

**Key things to check post-#170:**
- `gathered_context` is NOT tripled (no `---` separators between duplicated blocks)
- No `project_context` artifact in final state
- `resume_trace` is written by PD, not Facilitator

**Note:** Facilitator is procedural, so `llm_traces.jsonl` will NOT contain Facilitator entries (no LLM calls).

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  facilitator_specialist:
    is_enabled: true
    type: "procedural"  # No LLM config needed
```

### External MCP (filesystem)

```yaml
mcp:
  external_mcp:
    enabled: true
    services:
      filesystem:
        command: "docker"
        args: ["run", "-i", "--rm", "-v", "/workspace:/workspace", "mcp/filesystem", "/workspace"]
```

### Dependency Injection

`external_mcp_client` is injected by GraphBuilder after specialist instantiation.

---

## Key Files

| File | Purpose |
|------|---------|
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Facilitator implementation |
| [context_schema.py](../../app/src/interface/context_schema.py) | ContextPlan/ContextAction schemas |
| [context_engineering.py](../../app/src/workflow/subgraphs/context_engineering.py) | Subgraph edge definitions |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_triage_outcome()` routing logic |
| [external_client.py](../../app/src/mcp/external_client.py) | `sync_call_external_mcp()` bridge |
| [mcp/utils.py](../../app/src/mcp/utils.py) | `extract_text_from_mcp_result()` helper |
| [exit_interview_feedback.md](../../app/prompts/exit_interview_feedback.md) | EI feedback prompt template |

---

## Summary

The Facilitator is a **procedural MCP orchestrator** that:

1. Reads `triage_actions` from scratchpad (written by TriageArchitect)
2. Rebuilds `gathered_context` fresh each invocation (Task Strategy from SA's task_plan + EI feedback + trace knowledge + triage action results)
3. Produces a unified `gathered_context` artifact for downstream specialists
4. On BENIGN continuation (model was working, hit max_iterations), early returns with flag cleared
5. Does NOT accumulate across invocations, relay resume_trace, or invoke LLMs

Facilitator is the **sole writer of context** (#170). Specialists produce output artifacts; Facilitator curates them into `gathered_context`.
