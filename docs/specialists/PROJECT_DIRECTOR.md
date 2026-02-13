# Project Director Briefing: Autonomous Multi-Step Execution in LAS

**Purpose:** Technical briefing on the Project Director's role as the autonomous ReAct agent in LAS.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-12 (#170 context entity cleanup, #162 react_step migration)

---

## Executive Summary

The **Project Director (PD)** is an LLM-driven specialist that executes multi-step tasks autonomously via a ReAct loop. It bridges the gap between simple single-pass specialists and the need for iterative investigation, tool use, and action sequences.

Key characteristics:
- **ReAct loop via prompt-prix MCP** — PD owns the loop and tool dispatch; prompt-prix owns the LLM call (#162)
- **Context consumer, not producer** — receives all context via `gathered_context` from Facilitator (#170)
- **Fresh trace each invocation** — no resumption of prior traces on retry (#170)
- **Writes resume_trace** — the sole artifact PD produces for downstream consumption (EI, Facilitator)
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
classify_interrupt --> ExitInterview
    |
    [is_complete?]
    |-- YES --> END
    '-- NO  --> Facilitator --> Router --> PD (retry)
```

### Retry Path

```
PD writes resume_trace to artifacts
    |
classify_interrupt --> ExitInterview (reads resume_trace for operation inventory)
    |
    [INCOMPLETE]
    |
Facilitator:
  1. Rebuilds gathered_context fresh
  2. Extracts write operations from resume_trace (_extract_trace_knowledge)
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
_build_partial_result sets max_iterations_exceeded: True
    |
Facilitator: early return, clears flag, no context rebuild
    |
Router --> PD continues (fresh trace, same gathered_context)
```

---

## Data Flow Contract with Facilitator

PD and Facilitator have a strict division of responsibility (#170):

| Data | Writer | Reader | Mechanism |
|------|--------|--------|-----------|
| `gathered_context` | Facilitator | PD | `artifacts["gathered_context"]` injected into task prompt |
| `resume_trace` | PD | EI, Facilitator | `artifacts["resume_trace"]` via `operator.ior` merge |
| `user_request` | Triage | PD | `artifacts["user_request"]` — the original goal |
| `max_iterations_exceeded` | PD | Facilitator | `artifacts["max_iterations_exceeded"]` — triggers BENIGN path |

**PD never reads its own prior `resume_trace`.** Facilitator reads it and distills write operations into `gathered_context` as "Prior Work Completed." This prevents the stale-trace problem where the model re-feeds its prior conversation and thinks it already finished.

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

**Internal MCP** = Python services in-process (`self.mcp_client.call()`).
**External MCP** = Containerized services via stdio (`dispatch_external_tool()`).

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

Stagnation artifacts:
```python
{
    "resume_trace": trace,
    "stagnation_detected": True,
    "stagnation_tool": "read_file",
    "stagnation_args": {"path": "/workspace/test/1.txt"},
}
```

---

## Four Exit Paths

Every PD invocation ends via exactly one of four result builders:

| Exit Path | Trigger | Key Artifacts | Message |
|-----------|---------|---------------|---------|
| **Success** | Model chooses `DONE` | `resume_trace` | Model's `final_response` |
| **Error** | Exception or infra failure | `resume_trace` | Error description |
| **Stagnation** | Cycle detected in trace | `resume_trace`, `stagnation_detected`, `stagnation_tool`, `stagnation_args` | Repeated pattern + trace summary |
| **Partial** | `max_iterations` exceeded | `resume_trace`, `max_iterations_exceeded: True` | Tool counts + last 10 actions |

All four paths write `resume_trace` to artifacts. This is PD's primary output — it's the operation inventory that EI evaluates and Facilitator distills.

### Partial Result and BENIGN Continuation

When PD hits `max_iterations`, it sets `max_iterations_exceeded: True`. The graph routes through `classify_interrupt` to Exit Interview. If EI says INCOMPLETE (the model was making progress, just ran out of runway), Facilitator detects the BENIGN condition and early-returns, clearing the flag. Router then sends PD back with a fresh trace but the same `gathered_context`.

See [FACILITATOR.md](./FACILITATOR.md) "BENIGN Continuation" for the Facilitator side of this handshake.

---

## Graph Routing

### Post-PD Routing ([graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py))

```python
def after_project_director(self, state: GraphState) -> str:
    scratchpad = state.get("scratchpad", {})
    next_worker = scratchpad.get("next_worker")

    if next_worker == "web_specialist":
        return "web_specialist"
    elif next_worker == "router":
        return CoreSpecialist.ROUTER.value
    else:
        return CoreSpecialist.ROUTER.value  # Default
```

In practice, PD results flow through the standard hub-and-spoke: PD -> classify_interrupt -> Exit Interview -> Facilitator (if incomplete) -> Router.

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  project_director:
    is_enabled: true
    type: "hybrid"
    prompt_file: "project_director_prompt.md"
    description: "Emergent Deep Research Director"
    max_iterations: 15
    llm_config: "model_name_here"
```

`max_iterations` controls the react_step loop budget. Default is 15 if not specified.

### Dependency Injection

- `llm_adapter` — provides `model_name` and `system_prompt` for react_step calls
- `mcp_client` — internal MCP for search/browse
- `external_mcp_client` — external MCP for filesystem/terminal and prompt-prix react_step

---

## #170: What Changed

Before #170, PD maintained its own `ProjectContext` with `knowledge_base`, `open_questions`, and `project_state`. It also resumed prior traces via `_load_resume_trace()`.

| Before (#170) | After (#170) |
|----------------|--------------|
| `ProjectContext` with `knowledge_base` list | Deleted — Facilitator curates all context |
| `_get_or_init_context()` from artifacts | Goal from `artifacts["user_request"]` |
| `_update_context_from_trace()` duplicated entries | `Facilitator._extract_trace_knowledge()` — write ops only |
| `_load_resume_trace()` resumed stale trace | `trace = []` fresh start |
| `project_context` artifact in state | No private context artifacts |
| `research_status`, `iterations_used` artifacts | Removed — cosmetic, not consumed |
| `gathered_context` tripled on retry | Facilitator rebuilds fresh each invocation |

---

## Archive Forensics

```bash
# Check PD execution in routing history
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check resume_trace (PD's tool call log)
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.resume_trace'

# Check what context PD received
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.gathered_context'
```

**Key things to check post-#170:**
- No `project_context` artifact in final state
- `resume_trace` is a single-invocation trace (iteration numbers start at 0)
- `gathered_context` contains "Prior Work Completed" section on retry (not tripled)
- PD appears in `llm_traces.jsonl` (unlike Facilitator, PD triggers LLM calls via react_step)

---

## Key Files

| File | Purpose |
|------|---------|
| [project_director.py](../../app/src/specialists/project_director.py) | PD implementation — loop, dispatch, enrichment, result builders |
| [project_director_prompt.md](../../app/prompts/project_director_prompt.md) | System prompt — tool descriptions, process instructions, termination rules |
| [react_step.py](../../app/src/mcp/react_step.py) | Shared helpers: `ToolDef`, `call_react_step`, `build_tool_schemas`, `dispatch_external_tool` |
| [cycle_detection.py](../../app/src/resilience/cycle_detection.py) | `detect_cycle_with_pattern()` — stagnation detector |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `after_project_director()` routing |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Curates `gathered_context` for PD; extracts trace knowledge on retry |
| [FACILITATOR.md](./FACILITATOR.md) | Facilitator briefing — context assembly, BENIGN continuation, trace knowledge |

---

## Summary

The Project Director is a **ReAct loop controller** that:

1. Receives `user_request` as its goal and `gathered_context` as its working knowledge
2. Delegates LLM reasoning to prompt-prix via `react_step` MCP
3. Dispatches tool calls to filesystem, terminal, and web MCP services
4. Applies filesystem enrichments (error hints, path disambiguation) to help the model self-correct
5. Detects stagnation via cycle detection on tool call signatures
6. Writes `resume_trace` as its primary output artifact for EI and Facilitator consumption
7. Starts fresh each invocation (`trace = []`) — Facilitator provides retry knowledge via `gathered_context`

PD is a **context consumer** (#170). It reads `gathered_context` and writes `resume_trace`. Facilitator is the sole writer of context; PD is the sole writer of execution traces.
