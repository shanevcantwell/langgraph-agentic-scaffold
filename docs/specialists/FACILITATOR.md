# Facilitator Briefing: How Context Gathering Works in LAS

**Purpose:** Technical briefing on the Facilitator specialist's role in the LAS execution flow.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-25 (#223: RESEARCH action wired to webfetch-mcp web_search; ADR-045: subagent conciseness hint; ADR-077: signal processor, routing_context detection; #217: SA fail-fast conditional edge)

---

## Executive Summary

The **Facilitator** is a deterministic, non-LLM specialist that bridges planning (SA) and task execution (Router). It assembles context from task_plan, prior work, EI feedback, and triage actions into a unified `gathered_context` for downstream specialists.

Key characteristics:
- **Procedural, not LLM-based** — executes a plan, doesn't reason
- **Runs when SA succeeds** — conditional SA → Facilitator edge via `check_sa_outcome()` (#217). If SA fails to produce `task_plan`, the graph routes to END instead of Facilitator.
- **MCP orchestrator** — calls internal and external services via Model Context Protocol
- **Sole context writer** — specialists receive context via `gathered_context`, never accumulate their own (#170, ADR-071)
- **Fresh rebuild each invocation** — `gathered_context` rebuilt from scratch, but `accumulated_work` artifact persists across passes
- **Accumulated work tracking** — curates `specialist_activity` from scratchpad into `accumulated_work` artifact across retries

---

## Where Facilitator Fits in the Execution Flow

### First Pass (New Request)

```
User Request
    |
TriageArchitect (ACCEPT/REJECT gate, #199)
    |
    [check_triage_outcome]
    |-- PASS  --> SystemsArchitect (task_plan) --[check_sa_outcome]--> Facilitator --> Router --> Specialist
    '-- CLARIFY (ask_user only) --> EndSpecialist (reject with cause, #179)
```

Facilitator runs when SA produces a valid `task_plan` — wired via conditional SA → Facilitator edge (`check_sa_outcome()`, #217). If SA fails, the graph routes to END with a termination reason instead of proceeding with no plan. Context assembly runs regardless of whether triage_actions has entries.

### Retry Path (EI says INCOMPLETE)

```
Specialist (e.g., PD)
    |
SignalProcessor --> ExitInterview
    |
    [is_complete?]
    |-- YES --> END
    '-- NO  --> Facilitator (rebuild context + trace knowledge) --> Router --> Specialist
```

### BENIGN Continuation (max_iterations hit, model was working)

```
Specialist hits max_iterations (signals: {max_iterations_exceeded: True})
    |
SignalProcessor: routing_context = "benign_continuation" --> EI
    |
    [INCOMPLETE or no EI]
    |
Facilitator: detects routing_context == "benign_continuation", surfaces accumulated_work
    |
Router --> Specialist continues
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

### Context Assembly Order (#170, #173, #199)

Each invocation rebuilds `gathered_context` from scratch. The assembly order is:

0. **Subagent hint** (ADR-045) — if `scratchpad["subagent"]` is true, prepends `### Execution Mode: Subagent` with conciseness guidance. This replaces the old stringly-typed `[SUBAGENT]` prompt prefix with a structural system-prompt-layer injection. The hint lands in gathered_context regardless of which specialist gets routed.
1. **Task Strategy** — from `_build_task_context()`: `task_plan.plan_summary` + `execution_steps` + `acceptance_criteria` (#173). Full plan context so retry specialists have the complete strategy — not just a one-line summary.
2. **EI Retry Feedback + Prior Work** — from `_build_prior_work_section()`: accumulated operations + EI `missing_elements` + EI `recommended_specialists` guidance (only on retry)
3. **WIP Summary** — work-in-progress for BENIGN interrupts (when `routing_context == "benign_continuation"` in signals, #108)
4. **Plan Action Results** — RESEARCH, READ_FILE, SUMMARIZE, LIST_DIRECTORY, ASK_USER (from triage_actions if any)

### Action-by-Action Processing

| Action Type | MCP Service Called | Result |
|-------------|-------------------|--------|
| `RESEARCH` | External: `webfetch.web_search(query)` (#223) | Search results from SearXNG via webfetch-mcp |
| `READ_FILE` | External: `filesystem.read_file(path)` | File contents in code block |
| `SUMMARIZE` | Internal: `summarizer_specialist.summarize(text)` | Condensed summary |
| `LIST_DIRECTORY` | External: `filesystem.list_directory(path)` | Markdown bullet list with full paths |
| `ASK_USER` | LangGraph `interrupt()` | Pauses graph for user input, adds response to context |

**SUMMARIZE file path heuristic:** If the target looks like a file path (starts with `/` or `./`), Facilitator attempts to read the file first via filesystem MCP, then summarizes the content.

**ASK_USER:** Uses LangGraph's `interrupt()` primitive to pause execution. The user's answer is added to `gathered_context` as `### User Clarification`.

**LIST_DIRECTORY path enrichment:** Each entry includes the full path (e.g., `- [FILE] /workspace/test/1.txt`) so downstream specialists have unambiguous paths.

### Output: gathered_context + accumulated_work

```python
{
    "artifacts": {
        "gathered_context": """### Task Strategy
Categorize 13 files into topic subfolders based on content

**Execution steps:**
- List directory to enumerate files
- Read each file to determine topic category
- Create category subdirectories
- Move each file to its category directory

**Acceptance criteria:** All files in /workspace/test are moved into appropriate category subdirectories with no files remaining in the root test directory.

### Prior Work Completed
**Operations completed (4):**
- Created directory /workspace/test/animals
- Moved /workspace/test/1.txt -> /workspace/test/animals/1.txt
- Moved /workspace/test/4.txt -> /workspace/test/animals/4.txt
- Created directory /workspace/test/music

**EI recommends:** project_director — 9 files remain unsorted

### Directory: /workspace/test
- [FILE] /workspace/test/2.txt
- [FILE] /workspace/test/3.txt
- [DIR] /workspace/test/animals
- [DIR] /workspace/test/music""",
        "accumulated_work": [
            "Created directory /workspace/test/animals",
            "Moved /workspace/test/1.txt -> /workspace/test/animals/1.txt",
            "Moved /workspace/test/4.txt -> /workspace/test/animals/4.txt",
            "Created directory /workspace/test/music"
        ]
    },
    "scratchpad": {}
}
```

---

## Context Accumulation Architecture (#170, #199)

### gathered_context: Fresh Rebuild

Each invocation rebuilds `gathered_context` from scratch. No reading of prior `gathered_context` from artifacts. This prevents the tripling problem (before #170, identical Task Strategy + EI Feedback blocks got duplicated on every retry).

### accumulated_work: Cross-Pass Persistence

Facilitator curates `specialist_activity` into an `accumulated_work` artifact that persists across passes:

```python
# _accumulate_prior_work() — facilitator_specialist.py:186
existing = artifacts.get("accumulated_work", [])
new_activity = scratchpad.get("specialist_activity", [])
if new_activity:
    combined = existing + new_activity
    return combined
return existing
```

On retry, PD on pass N sees operations from passes 1 through N-1. Without this, PD only sees the latest pass's operations due to scratchpad's ior (last-writer-wins) merge.

### Shared Helpers

Three helpers separate concerns:
- **`_accumulate_prior_work(artifacts, scratchpad)`** — curates specialist_activity into accumulated_work list
- **`_build_task_context(artifacts)`** — builds Task Strategy with plan_summary + execution_steps + acceptance_criteria
- **`_build_prior_work_section(accumulated_work, exit_interview_result)`** — formats accumulated operations + EI guidance

Both BENIGN and normal retry paths use these shared helpers.

### Why Not Pass the Full Trace?

PD starts with `trace = []` each invocation (#170 Step 3). The model gets a fresh start but knows what write operations already succeeded via `gathered_context`. This avoids the stale-trace problem where the model re-feeds its prior conversation and thinks it already finished.

The full react trace is captured separately to `scratchpad["react_trace"]` for observability (state_timeline, archive) — but Facilitator never reads it. Only the human-readable activity summary enters `gathered_context`.

---

## BENIGN Continuation (#114)

When PD (or any specialist) hits max_iterations, it writes `max_iterations_exceeded: True` to the `signals` field. SignalProcessor classifies this as BENIGN and sets `routing_context: "benign_continuation"` in its output signals. Facilitator detects this via `state.get("signals", {}).get("routing_context") == "benign_continuation"`.

- Accumulates `specialist_activity` into `accumulated_work` artifact (same as normal retry)
- Builds WIP summary and prior work context so Router can make an informed continuation decision
- Does NOT re-execute triage_actions (no MCP calls for context gathering)
- The `signals` replace reducer handles clearing — Facilitator no longer needs to clear any flags

Two scenarios qualify as BENIGN:
1. **Pure BENIGN:** `routing_context == "benign_continuation"` + no EI result (interrupted before EI ran)
2. **BENIGN after EI:** `routing_context == "benign_continuation"` + EI said INCOMPLETE (model was working, EI judged)

---

## MCP Integration Details

### Internal MCP (Python services in-process)

Called via `self.mcp_client.call()`:

```python
results = self.mcp_client.call(
    service_name="summarizer_specialist",
    function_name="summarize",
    text="..."
)
```

### External MCP (Containerized services via stdio)

Called via the sync-to-async bridge `sync_call_external_mcp()`, with results parsed by `extract_text_from_mcp_result()`:

```python
# Filesystem MCP (file operations)
content = sync_call_external_mcp(
    self.external_mcp_client,
    "filesystem",
    "read_file",
    {"path": "/workspace/config.yaml"}
)

# Webfetch MCP (web search via SearXNG, #223)
results = sync_call_external_mcp(
    self.external_mcp_client,
    "webfetch",
    "web_search",
    {"query": action.target}
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
| Track accumulated work | Yes | Curates `specialist_activity` from scratchpad into `accumulated_work` artifact |
| Write execution traces | No | PD writes `specialist_activity` to scratchpad; Facilitator reads it directly |

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

**Key things to check:**
- `gathered_context` is NOT tripled (no `---` separators between duplicated blocks)
- `accumulated_work` artifact is present on retry paths (cumulative list)
- No `project_context` artifact in final state
- `specialist_activity` is written by PD to scratchpad, not Facilitator

**Note:** Facilitator is procedural (no LLM calls), but SafeExecutor still emits traces for it in `llm_traces.jsonl` (ADR-073 Phase 1: traces for ALL specialists). The trace captures artifacts produced and scratchpad signals, not LLM request/response.

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  facilitator_specialist:
    is_enabled: true
    type: "procedural"  # No LLM config needed
```

### External MCP (filesystem + webfetch)

```yaml
mcp:
  external_mcp:
    enabled: true
    services:
      filesystem:
        command: "docker"
        args: ["exec", "-i", "filesystem-mcp", "node", "/app/dist/index.js", "/workspace"]
      webfetch:
        command: "docker"
        args: ["exec", "-i", "webfetch-mcp", "node", "/app/server.mjs"]
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
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_triage_outcome()` and `check_sa_outcome()` routing logic (#217) |
| [external_client.py](../../app/src/mcp/external_client.py) | `sync_call_external_mcp()` bridge |
| [mcp/utils.py](../../app/src/mcp/utils.py) | `extract_text_from_mcp_result()` helper |
| [exit_interview_feedback.md](../../app/prompts/exit_interview_feedback.md) | EI feedback prompt template |

---

## Summary

The Facilitator is a **procedural MCP orchestrator** that:

1. Runs when SA succeeds — conditional SA → Facilitator edge via `check_sa_outcome()` (#217); Facilitator → Router is unconditional
2. Rebuilds `gathered_context` fresh each invocation (Task Strategy + execution_steps + acceptance_criteria from task_plan, EI feedback, accumulated prior work, triage action results)
3. Accumulates `specialist_activity` into `accumulated_work` artifact across retries
4. Produces a unified `gathered_context` artifact for downstream specialists
5. On BENIGN continuation (model was working, hit max_iterations), surfaces continuation context with flag cleared
6. Does NOT invoke LLMs — all context assembly is procedural

Facilitator is the **sole writer of context** (#170, ADR-071). Specialists produce output artifacts; Facilitator curates them into `gathered_context`.
