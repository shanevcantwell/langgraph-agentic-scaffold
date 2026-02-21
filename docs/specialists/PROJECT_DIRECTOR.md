# Project Director Briefing: Autonomous Multi-Step Execution in LAS

**Purpose:** Technical briefing on the Project Director's role as the autonomous ReAct agent in LAS.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-20 (ADR-045: fork() with conditioning frame + expected_artifacts (#205, #206); ADR-077: routing signals, signal processor)

---

## Executive Summary

The **Project Director (PD)** is an LLM-driven specialist that executes multi-step tasks autonomously via a ReAct loop. It bridges the gap between simple single-pass specialists and the need for iterative investigation, tool use, and action sequences.

Key characteristics:
- **ReAct loop via prompt-prix MCP** — PD owns the loop and tool dispatch; prompt-prix owns the LLM call (#162)
- **Context consumer, not producer** — receives all context via `gathered_context` from Facilitator (#170)
- **Fresh trace each invocation** — no resumption of prior traces on retry (#170)
- **Artifact tools (read + write)** — mid-execution persistence via `write_artifact` (ADR-076). Observations, decisions, and progress survive max_iterations and retries.
- **Writes `specialist_activity` + `react_trace` to scratchpad** — observability signals for Facilitator (retry context) and state_timeline (archive/SSE)
- **Stagnation detection** — cycle detection catches repeating tool call patterns
- **Filesystem enrichment** — error hints and path disambiguation for model self-correction

---

## Where PD Fits in the Execution Flow

### First Pass (New Request)

```
User Request
    |
TriageArchitect --> Facilitator (gathers context) --> Router
    |
    [Router selects project_director]
    |
PD: react_step loop (up to max_iterations)
    |
SignalProcessor --> ExitInterview
    |
    [is_complete?]
    |-- YES --> END
    '-- NO  --> Facilitator --> Router --> PD (retry)
```

### Retry Path

```
PD writes specialist_activity to scratchpad
    |
SignalProcessor --> ExitInterview
    |
    [INCOMPLETE]
    |
Facilitator:
  1. Rebuilds gathered_context fresh
  2. Reads specialist_activity list from scratchpad (human-readable write operations)
  3. Adds EI feedback (missing_elements + reasoning)
    |
Router --> PD:
  - Reads gathered_context (includes "Prior Work Completed" section)
  - Starts with trace = [] (fresh)
  - Re-discovers workspace state via list_directory/read_file
```

### BENIGN Continuation (max_iterations hit)

```
PD hits max_iterations
    |
_build_partial_result sets signals: {max_iterations_exceeded: True}
    |
SignalProcessor: routing_context = "benign_continuation" --> EI
    |
Facilitator: BENIGN early return, surfaces accumulated_work
    |
Router --> PD continues (fresh trace, same gathered_context)
```

---

## Data Flow Contract with Facilitator

PD and Facilitator have a strict division of responsibility (#170):

| Data | Writer | Reader | Mechanism |
|------|--------|--------|-----------|
| `gathered_context` | Facilitator | PD | `artifacts["gathered_context"]` injected into task prompt |
| `specialist_activity` | PD | Facilitator | `scratchpad["specialist_activity"]` — human-readable write operation summary |
| `react_trace` | PD | state_timeline | `scratchpad["react_trace"]` — full tool call + observation history (observability only) |
| `captured_artifacts` | PD | LangGraph ior merge | All artifacts (including mid-loop `write_artifact` writes) propagated through all four result builders (ADR-076) |
| `user_request` | Triage | PD | `artifacts["user_request"]` — the original goal |
| `max_iterations_exceeded` | PD | SignalProcessor | `signals["max_iterations_exceeded"]` — triggers BENIGN path (ADR-077) |
| `stagnation_detected` + tool/args | PD | SignalProcessor | `signals["stagnation_detected"]` — triggers PATHOLOGICAL path (ADR-077) |

**PD never reads its own prior output.** Facilitator reads `specialist_activity` from scratchpad and surfaces it in `gathered_context` as "Prior Work Completed." This prevents the stale-trace problem where the model re-feeds its prior conversation and thinks it already finished.

**PD never writes to `gathered_context`.** This is Facilitator's exclusive domain.

### What PD Sees on Retry

```
**Goal:** Organize files in /workspace/test into category subfolders based on content

**System Context (gathered before your invocation):**
### Task Strategy
User wants files sorted by content into category subfolders

### Retry Context (from Exit Interview evaluation)
**What still needs to be done:** 4 files still need moving
**Why incomplete:** Only 2 of 6 files were categorized

### Prior Work Completed
- Created directory /workspace/test/animals
- Moved /workspace/test/1.txt -> /workspace/test/animals/1.txt
- Moved /workspace/test/4.txt -> /workspace/test/animals/4.txt

### Directory: /workspace/test
- [FILE] /workspace/test/2.txt
- [FILE] /workspace/test/3.txt
- [DIR] /workspace/test/animals
```

PD then starts a fresh `trace = []`, re-reads files 2.txt and 3.txt to understand their content, and acts on the remaining work.

---

## The react_step Loop

PD delegates LLM reasoning to prompt-prix via the `react_step` MCP tool. This means PD itself contains **no LLM invocation code** — it's a loop controller and tool dispatcher.

```
            PD (_execute_logic)                 prompt-prix MCP
            ─────────────────                   ───────────────
                    |
    ┌──────────────>|
    |               | ──call_react_step()──>  react_step(model, prompt, trace, tools)
    |               |                              |
    |               |                         LLM call with tool schemas
    |               |                              |
    |               | <────────────────────  {pending_tool_calls: [...]}
    |               |                        or {completed: true, final_response: "..."}
    |               |
    |          [completed?]
    |          YES: return _build_success_result
    |          NO:  dispatch each pending tool call
    |               |
    |          _dispatch_tool_call()
    |               | ──fork (las)──>    dispatch_fork() → subagent LAS invocation (ADR-045)
    |               | ──external MCP──>  filesystem / terminal
    |               | ──internal MCP──>  web_specialist / browse_specialist
    |               |
    |          append {tool_call, observation, success} to trace
    |               |
    |          _check_stagnation(trace)
    |          STAGNATION: return _build_stagnation_result
    |               |
    └───────────────┘  (next iteration)
```

---

## Prompt and Context Assembly

PD itself makes **no LLM calls**. It assembles a prompt structure and sends it to prompt-prix MCP, which owns the actual LLM invocation. Understanding what the model sees requires tracing through the full assembly chain.

### Loading Chain: Config to System Prompt

```
config.yaml
  specialists.project_director.prompt_file: "project_director_prompt.md"
  specialists.project_director.llm_config: "lmstudio"
    │
    ▼
GraphBuilder._attach_llm_adapter()          [graph_builder.py:249]
    │
    ├── load_prompt("project_director_prompt.md")   [prompt_loader.py:24]
    │   reads: APP_ROOT/prompts/project_director_prompt.md
    │   returns: system_prompt (str)
    │
    ├── (optional) append tool descriptions if specialist has `tools:` config
    │
    └── AdapterFactory.create_adapter(name, system_prompt)  [factory.py:179]
        │
        └── LMStudioAdapter(system_prompt=system_prompt)
            stores: self.system_prompt = "<full prompt text>"
```

PD reads these at the top of `_execute_logic()`:

```python
model_id = getattr(self.llm_adapter, 'model_name', None) or "default"
system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
```

### Three Layers of What the Model Sees

Each `call_react_step()` sends three conceptual layers to prompt-prix:

**Layer 1: System Prompt** — static identity and behavioral instructions

The full text of [project_director_prompt.md](../../app/prompts/project_director_prompt.md). This defines:
- PD's identity ("You are the **Project Director**, an autonomous agent...")
- Available tool categories (web research, filesystem, terminal)
- Process flow (Analyze → Call tools → Iterate → Complete)
- Termination rules (`DONE` with `final_response` to finish)
- Efficiency guidance (use `run_command` for bulk operations)
- When to stop (information tasks vs. action tasks)

This prompt is **identical across all invocations** of the same PD instance. It never changes between retries.

**Layer 2: Task Prompt** — the specific goal and context for this invocation

Built by `_build_task_prompt()`:

```python
def _build_task_prompt(self, user_request: str, state: dict) -> str:
    gathered_context = state.get("artifacts", {}).get("gathered_context", "")
    context_section = ""
    if gathered_context:
        context_section = f"\n**System Context (gathered before your invocation):**\n{gathered_context}\n"
    return f"**Goal:** {user_request}\n{context_section}"
```

This produces a string like:

```
**Goal:** Organize files in /workspace/test into category subfolders based on content

**System Context (gathered before your invocation):**
### Task Strategy
User wants files sorted by content into category subfolders

### Retry Context (from Exit Interview evaluation)
**What still needs to be done:** 4 files still need moving
**Why incomplete:** Only 2 of 6 files were categorized

### Prior Work Completed
- Created directory /workspace/test/animals
- Moved /workspace/test/1.txt -> /workspace/test/animals/1.txt

### Directory: /workspace/test
- [FILE] /workspace/test/2.txt
- [FILE] /workspace/test/3.txt
- [DIR] /workspace/test/animals
```

Key data sources:
- `user_request` — from `artifacts["user_request"]` (written by Triage)
- `gathered_context` — from `artifacts["gathered_context"]` (written by Facilitator, see [FACILITATOR.md](./FACILITATOR.md) "Context Assembly Order")

The task prompt **changes between retries** because Facilitator rebuilds `gathered_context` fresh each time (with updated EI feedback, updated trace knowledge, and current filesystem state).

**Layer 3: Trace** — accumulated tool call history within the current invocation

The `trace` list grows during a single PD invocation. Each entry records one tool call and its result:

```python
# Trace entry structure (appended in _execute_logic)
{
    "iteration": 2,                  # Which react_step loop iteration
    "tool_call": {
        "id": "call_5",             # Unique ID for this call
        "name": "read_file",        # Tool name from _build_tools()
        "args": {                   # Arguments passed to the tool
            "path": "/workspace/test/2.txt"
        }
    },
    "observation": "This file contains information about cats and dogs.",  # Tool result string
    "success": True,                 # False if observation starts with "Error:"
    "thought": "I need to read this file to determine its category."  # Model reasoning (optional)
}
```

On iteration 0, `trace = []` — the model sees only the system prompt, task prompt, and tool schemas. On iteration N, the model sees the full history of tool calls and observations from iterations 0 through N-1.

### What prompt-prix Receives

`call_react_step()` sends this parameter dict to prompt-prix MCP via `sync_call_external_mcp()`:

```python
{
    "model_id": "gpt-oss-20b",              # Which model to call
    "system_prompt": "<PD prompt file>",     # Layer 1: identity/behavior
    "initial_message": "<task prompt>",      # Layer 2: goal + gathered_context
    "trace": [                               # Layer 3: tool call history
        {"iteration": 0, "tool_call": {...}, "observation": "...", ...},
        {"iteration": 1, "tool_call": {...}, "observation": "...", ...},
    ],
    "mock_tools": None,                      # None = tool-forwarding mode
    "tools": [                               # Tool schemas in OpenAI format
        {"type": "function", "function": {"name": "search", "description": "...", "parameters": {...}}},
        {"type": "function", "function": {"name": "list_directory", ...}},
        ...
    ],
    "call_counter": 5                        # For generating unique tool call IDs
}
```

prompt-prix assembles these into an OpenAI-compatible chat completion request. Because `mock_tools=None`, prompt-prix returns `pending_tool_calls` instead of executing tools itself — PD dispatches them.

### prompt-prix Response

prompt-prix returns either:

**Completion** (model chose `DONE`):
```json
{"completed": true, "final_response": "Organized 6 files into 3 categories: ..."}
```

**Tool calls** (model wants to use tools):
```json
{
    "completed": false,
    "pending_tool_calls": [
        {"id": "call_6", "name": "read_file", "args": {"path": "/workspace/test/3.txt"}},
        {"id": "call_7", "name": "read_file", "args": {"path": "/workspace/test/5.txt"}}
    ],
    "thought": "I need to read the remaining files to categorize them.",
    "call_counter": 8
}
```

### Context Window Growth

The model's effective context grows with each iteration:

```
Iteration 0:  system_prompt + task_prompt + tool_schemas
Iteration 1:  ... + trace[0] (one tool call + observation)
Iteration 5:  ... + trace[0..4] (five tool calls + observations)
Iteration 14: ... + trace[0..13] (fourteen tool calls + observations)
```

This is why `max_iterations` matters — each iteration adds to the context window. For a 13-file categorization task, a typical run uses 20-30 tool calls across ~15 iterations (list dir, read 13 files, create dirs, move 13 files).

### Tool Schemas (OpenAI Function Calling Format)

`build_tool_schemas()` merges `ToolDef.description` with `_TOOL_PARAMS` to produce:

```json
[
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web for information. Args: query (str).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and directories. Args: path (str).",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directory path to list"}},
                "required": ["path"]
            }
        }
    }
]
```

These schemas tell the LLM (via logit masking in LM Studio) what tools exist and their argument shapes.

---

## Tool Definitions

### Active Tools (wired in `_build_tools`)

| Tool | MCP Service | Type | Purpose |
|------|-------------|------|---------|
| `search` | `web_specialist` | Internal | Web search queries |
| `browse` | `browse_specialist` | Internal | Fetch and parse a URL |
| `list_directory` | `filesystem` | External | List files/dirs at a path |
| `read_file` | `filesystem` | External | Read file contents |
| `create_directory` | `filesystem` | External | Create a directory |
| `move_file` | `filesystem` | External | Move or rename a file |
| `run_command` | `terminal` | External | Execute a shell command |
| `list_artifacts` | `local` | Local | List available artifacts with type/size hints |
| `retrieve_artifact` | `local` | Local | Retrieve full content of an artifact by key |
| `write_artifact` | `local` | Local | Persist observation, decision, or progress as an artifact (ADR-076) |
| `fork` | `las` | Local (ADR-045) | Spawn subagent via `graph.invoke()` for independent subtask (context-isolated, runs full LAS including EI). Supports `expected_artifacts` for structured result extraction (#206). |

**Internal MCP** = Python services in-process (`self.mcp_client.call()`).
**External MCP** = Containerized services via stdio (`dispatch_external_tool()`).
**Local** = In-process dispatch on `captured_artifacts` snapshot (`dispatch_artifact_tool()`).

### fork() — Conditioning Frame and Expected Artifacts (#205, #206)

Every child spawned via `fork` receives a **conditioning frame** prepended to its prompt:

> "This is a development environment where failures are expected and informative. If a tool fails, a capability is unavailable, or you cannot complete the task, report exactly what happened and what you tried. A clear failure report is more valuable than a simulated or fabricated result. Never generate synthetic data to stand in for real tool output."

This reframes the reward landscape so that "good output" and "honest output" point the same direction. Without it, small models (qwen3-30b, gpt-oss-20b) fabricate realistic-looking tool results when real tools fail — the completion attractor overwhelms honesty (#205).

PD can also specify **expected_artifacts** — a list of artifact keys the child should write its results to:

```json
{
    "name": "fork",
    "args": {
        "prompt": "Analyze the contents of /workspace/data/report.csv",
        "context": "...",
        "expected_artifacts": ["csv_analysis", "row_count"]
    }
}
```

When `expected_artifacts` is provided:
1. `_build_child_prompt()` procedurally appends write instructions to the child's prompt
2. The child writes results via `write_artifact` to the specified keys
3. `extract_fork_result()` returns only those artifact values as key-value pairs
4. Missing keys are logged and reported in the result string

When `expected_artifacts` is omitted, the standard extraction chain applies: `final_user_response.md` → `error_report` → last message fallback.

### Note: `write_file`

`write_file` has a parameter schema defined in `_TOOL_PARAMS` but is **not wired** in `_build_tools()`. The prompt file mentions it in example flows. If a model attempts to call `write_file`, it will get `Error: Unknown tool 'write_file'`. This is a known gap — the tool exists in schema but isn't registered as a ToolDef.

---

## Filesystem Enrichment Helpers

PD applies two post-processing enrichments to filesystem tool results. These are PD-specific context engineering that help the model self-correct without wasting iterations.

### `_enrich_filesystem_error()`

When a filesystem operation fails with ENOENT, EISDIR, EACCES, or ENOTDIR, PD checks `successful_paths` (accumulated during the current trace) for similar paths:

```python
# Error: ENOENT: no such file or directory: '1.txt'
#
# Hint: You previously succeeded with: /workspace/test/1.txt
# Did you forget the directory prefix?
```

This prevents the common failure mode where a model forgets the directory prefix after listing files.

### `_enrich_list_directory_result()`

Prepends the queried directory path to each entry, turning relative names into absolute paths:

```
# Before enrichment:        # After enrichment:
[FILE] 1.txt                [FILE] /workspace/test/1.txt
[FILE] 2.txt                [FILE] /workspace/test/2.txt
[DIR] animals               [DIR] /workspace/test/animals
```

This eliminates path ambiguity — the model sees full paths and uses them directly in subsequent tool calls.

---

## Stagnation Detection

After each iteration, PD extracts tool call signatures `(name, args)` from the trace and runs `detect_cycle_with_pattern()`:

```python
period, _pattern = detect_cycle_with_pattern(
    signatures, min_repetitions=self.CYCLE_MIN_REPETITIONS  # 3
)
```

If a repeating pattern of length N is found repeated 3+ times, PD exits with `_build_stagnation_result()`. The stagnation message includes the repeated tool name, args, and a trace summary.

Stagnation output:
```python
# signals (routing, ADR-077):
{
    "stagnation_detected": True,
    "stagnation_tool": "read_file",
    "stagnation_args": {"path": "/workspace/test/1.txt"},
}
# scratchpad (observability):
{
    "specialist_activity": ["Read /workspace/test/1.txt", ...],
    "react_trace": [{"tool_call": {...}, "observation": "...", "success": True}, ...],
}
```

---

## Four Exit Paths

Every PD invocation ends via exactly one of four result builders:

| Exit Path | Trigger | Artifacts | Scratchpad | Message |
|-----------|---------|-----------|------------|---------|
| **Success** | Model chooses `DONE` | `captured_artifacts` (all written artifacts) | `specialist_activity`, `react_trace` | Model's `final_response` |
| **Error** | Exception or infra failure | `captured_artifacts` (all written artifacts) | `specialist_activity`, `react_trace` | Error description |
| **Stagnation** | Cycle detected in trace | `captured_artifacts` | `specialist_activity`, `react_trace` | Repeated pattern + trace summary |
| **Partial** | `max_iterations` exceeded | `captured_artifacts` | `specialist_activity`, `react_trace` | Tool counts + last 10 actions |

**Signals field (ADR-077):** Stagnation writes `stagnation_detected`, `stagnation_tool`, `stagnation_args` to `signals`. Partial writes `max_iterations_exceeded` to `signals`. These are routing signals consumed by SignalProcessor — they no longer live in artifacts.

All four paths propagate `captured_artifacts` — any artifact written via `write_artifact` during the react loop survives in state (ADR-076). This is critical for the Partial path: observations and decisions persist even when PD runs out of iteration budget.

All four paths also write `specialist_activity` (human-readable) and `react_trace` (full tool history) to scratchpad. `specialist_activity` is PD's primary output for downstream consumption — Facilitator reads it to build "Prior Work Completed" context on retry. `react_trace` is observability-only (state_timeline, archive).

### Partial Result and BENIGN Continuation

When PD hits `max_iterations`, it writes `max_iterations_exceeded: True` to the `signals` field. All artifacts written via `write_artifact` during the react loop are included in `captured_artifacts` and propagated to state (ADR-076). SignalProcessor classifies this as BENIGN and routes to Exit Interview with `routing_context: "benign_continuation"`. If EI says INCOMPLETE (the model was making progress, just ran out of runway), Facilitator detects the BENIGN condition via `routing_context` and early-returns. Router then sends PD back with a fresh trace but the same `gathered_context`. Written artifacts remain discoverable via `list_artifacts`/`retrieve_artifact` on the next invocation.

See [FACILITATOR.md](./FACILITATOR.md) "BENIGN Continuation" for the Facilitator side of this handshake.

---

## Graph Routing

### Post-PD Routing (ADR-077: Signal Processor)

PD results flow through the standard hub-and-spoke via SignalProcessor:

```
PD → SignalProcessor → route_from_signal → {EI, Router, END, ...}
```

SignalProcessor reads PD's `signals` field to classify the interrupt type:
- **Normal (artifacts present):** → Exit Interview for completion check
- **BENIGN (max_iterations_exceeded):** → Exit Interview with `routing_context: "benign_continuation"`
- **PATHOLOGICAL (stagnation_detected):** → Interrupt Evaluator → EI → Router (fallback chain)

See [SIGNAL_PROCESSOR.md](./SIGNAL_PROCESSOR.md) for the full priority chain.

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  project_director:
    is_enabled: true
    type: "llm"
    prompt_file: "project_director_prompt.md"
    description: "Executes multi-step tasks autonomously..."
    max_iterations: 50
    llm_config: "model_name_here"
```

`max_iterations` controls the react_step loop budget. Currently set to 50 in config.yaml.

### Dependency Injection

- `llm_adapter` — provides `model_name` and `system_prompt` for react_step calls
- `mcp_client` — internal MCP for search/browse
- `external_mcp_client` — external MCP for filesystem/terminal and prompt-prix react_step

---

## #170: What Changed

Before #170, PD maintained its own `ProjectContext` with `knowledge_base`, `open_questions`, and `project_state`. It also resumed prior traces via `_load_resume_trace()`.

| Before (#170) | After (#170 + ADR-073) |
|----------------|------------------------|
| `ProjectContext` with `knowledge_base` list | Deleted — Facilitator curates all context |
| `_get_or_init_context()` from artifacts | Goal from `artifacts["user_request"]` |
| `_update_context_from_trace()` duplicated entries | `specialist_activity` in scratchpad — write ops only |
| `_load_resume_trace()` resumed stale trace | `trace = []` fresh start |
| `resume_trace` artifact in state | `specialist_activity` + `react_trace` in scratchpad (ADR-073 Phase 3-4) |
| `project_context` artifact in state | No private context artifacts |
| `research_status`, `iterations_used` artifacts | Removed — cosmetic, not consumed |
| `gathered_context` tripled on retry | Facilitator rebuilds fresh each invocation |

---

## Archive Forensics

```bash
# Check PD execution in routing history
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check specialist_activity (human-readable work summary)
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.scratchpad.specialist_activity'

# Check react_trace (full tool call + observation history)
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.scratchpad.react_trace'

# Check state_timeline for PD's entry (includes react_trace + prompts)
unzip -p ./logs/archive/run_*.zip state_timeline.jsonl | grep project_director | jq .

# Check what context PD received
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.gathered_context'
```

**Key things to check:**
- No `project_context` artifact in final state
- `specialist_activity` is a list of human-readable strings (write operations)
- `react_trace` captures full tool call history with observations
- `gathered_context` contains "Prior Work Completed" section on retry (not tripled)
- PD appears in `llm_traces.jsonl` and `state_timeline.jsonl`

---

## Key Files

| File | Purpose |
|------|---------|
| [project_director.py](../../app/src/specialists/project_director.py) | PD implementation — loop, dispatch, enrichment, result builders |
| [project_director_prompt.md](../../app/prompts/project_director_prompt.md) | System prompt — tool descriptions, process instructions, termination rules |
| [react_step.py](../../app/src/mcp/react_step.py) | Shared helpers: `ToolDef`, `call_react_step`, `build_tool_schemas`, `dispatch_external_tool` |
| [artifact_tools.py](../../app/src/mcp/artifact_tools.py) | `list_artifacts`, `retrieve_artifact`, `write_artifact`, dispatch, name generation (ADR-076) |
| [fork.py](../../app/src/mcp/fork.py) | `dispatch_fork()` + `extract_fork_result()` — recursive LAS invocation via `graph.invoke()` with conditioning frame (#205) and `expected_artifacts` (#206) |
| [cycle_detection.py](../../app/src/resilience/cycle_detection.py) | `detect_cycle_with_pattern()` — stagnation detector |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `after_project_director()` routing |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Curates `gathered_context` for PD; extracts trace knowledge on retry |
| [FACILITATOR.md](./FACILITATOR.md) | Facilitator briefing — context assembly, BENIGN continuation, trace knowledge |

---

## Summary

The Project Director is a **ReAct loop controller** that:

1. Receives `user_request` as its goal and `gathered_context` as its working knowledge
2. Delegates LLM reasoning to prompt-prix via `react_step` MCP
3. Dispatches tool calls to filesystem, terminal, web MCP services, and local artifact tools
4. Persists observations, decisions, and progress via `write_artifact` — surviving max_iterations and retries (ADR-076)
5. Applies filesystem enrichments (error hints, path disambiguation) to help the model self-correct
6. Detects stagnation via cycle detection on tool call signatures
7. Writes `specialist_activity` (human-readable) and `react_trace` (full tool history) to scratchpad
8. Starts fresh each invocation (`trace = []`) — Facilitator provides retry knowledge via `gathered_context`

PD is a **context consumer** (#170). It reads `gathered_context` and writes execution activity to scratchpad. Facilitator is the sole writer of context; PD is the sole writer of execution activity. Written artifacts (ADR-076) provide a second channel: other specialists can discover PD's observations via `list_artifacts`/`retrieve_artifact` without Facilitator mediation.
