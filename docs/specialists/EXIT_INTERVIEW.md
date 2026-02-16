# Exit Interview Briefing: Verification Gate Before Termination in LAS

**Purpose:** Technical briefing on the Exit Interview specialist's role as the verification gate before END.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-16 (#195: react_step-only architecture, shared artifact tools, no fallback path)

---

## Executive Summary

The **Exit Interview (EI)** is a verification agent that gates the END node. Before any workflow terminates, EI inspects the filesystem and artifacts using tools, then renders a structured pass/fail judgment. If the task is incomplete, EI names the missing work and recommends which specialist should handle it.

Key characteristics:
- **react_step tool loop via prompt-prix MCP** — EI owns the loop and tool dispatch; prompt-prix owns the LLM call (#195)
- **Tool-first verification** — EI must call at least one verification tool before rendering judgment (#193)
- **Final-state-only observer** — EI cannot see original or intermediate states; it verifies expected end state
- **Lazy exit_plan via SA MCP** — EI calls Systems Architect on first invocation to produce verification criteria (#115)
- **No fallback path** — if prompt-prix is unavailable, EI returns an honest "cannot verify" signal (#195)
- **Graph-wired, not Router-selected** — invoked automatically by `check_task_completion` and `classify_interrupt`
- **Shared artifact tools** — `list_artifacts` and `retrieve_artifact` extracted to `mcp/artifact_tools.py` for use by any specialist

---

## Where EI Fits in the Execution Flow

### Specialist Claims Complete

```
Specialist sets task_is_complete = True
    |
check_task_completion (graph_orchestrator.py)
    |
    [Last specialist in SKIP_EXIT_INTERVIEW?]
    |-- YES --> END (default_responder, chat, tiered_synthesizer)
    '-- NO  --> exit_interview_specialist
                    |
              after_exit_interview
                    |
                    [is_complete?]
                    |-- YES --> END
                    '-- NO  --> Facilitator --> Router --> Specialist (retry)
```

### BENIGN Continuation (max_iterations hit)

```
Specialist hits max_iterations
    |
classify_interrupt (graph_orchestrator.py)
    |
    [max_iterations_exceeded?]
    |-- YES --> exit_interview_specialist (for feedback)
                    |
              after_exit_interview
                    |
                    [INCOMPLETE]
                    |
              Facilitator: BENIGN early return, clears flag
                    |
              Router --> Specialist continues
```

### Unproductive Loop Detected

```
check_task_completion or route_after_router detects loop
    |
    --> exit_interview_specialist
              |
        after_exit_interview
              |
              [INCOMPLETE + loop_detected?]
              |-- YES --> END (abort with termination_reason)
              '-- NO  --> Facilitator --> Router (normal retry)
```

---

## The react_step Verification Loop

EI delegates LLM reasoning to prompt-prix via `react_step` MCP. Like PD, EI itself contains no LLM invocation code — it's a loop controller and tool dispatcher.

```
          EI (_verify)                        prompt-prix MCP
          ──────────                          ───────────────
                  |
  ┌──────────────>|
  |               | ──call_react_step()──>  react_step(model, prompt, trace, tools)
  |               |                              |
  |               |                         LLM call with tool schemas
  |               |                              |
  |               | <────────────────────  {pending_tool_calls: [...]}
  |               |                        or {completed: true, done_args: {...}}
  |               |
  |          [completed + DONE?]
  |          YES: parse CompletionEvaluation
  |               |
  |          [tool-use-before-DONE guard (#193)]
  |          NO PRIOR TOOL USE: inject nudge, continue loop
  |          HAS TOOL USE: return evaluation
  |               |
  |          NO:  dispatch each pending tool call
  |               |
  |          _dispatch_tool()
  |               | ──external MCP──>  filesystem (list_directory, read_file)
  |               | ──local──>         artifact_tools (list_artifacts, retrieve_artifact)
  |               |
  |          append {tool_call, observation, success} to trace
  |               |
  └───────────────┘  (next iteration, up to MAX_ITERATIONS=8)
```

### Tool-Use-Before-DONE Guard (#193)

If the model calls DONE without having made any prior tool calls, EI injects a system nudge into the trace:

> "You must call at least one verification tool (list_directory, read_file, list_artifacts, retrieve_artifact) before calling DONE. Verify real outcomes first."

This prevents EI from rubber-stamping completion based on artifact summaries or message content. The model must inspect something real before rendering judgment.

### Max Iterations Without DONE

If the loop exhausts `MAX_ITERATIONS` (8) without the model calling DONE, EI defaults to incomplete:

```python
CompletionEvaluation(
    is_complete=False,
    reasoning="Verification did not complete within 8 iterations",
    missing_elements="EI verification loop exhausted without reaching a conclusion",
)
```

This is conservative by design — the cost of one more routing cycle is much lower than a premature termination.

---

## Tool Definitions

### Active Tools (wired in `_build_tools`)

| Tool | Service | Type | Purpose |
|------|---------|------|---------|
| `list_directory` | `filesystem` | External MCP | List files/dirs at a path |
| `read_file` | `filesystem` | External MCP | Read file contents |
| `list_artifacts` | local | Shared (`mcp/artifact_tools.py`) | List artifact keys with type/size hints |
| `retrieve_artifact` | local | Shared (`mcp/artifact_tools.py`) | Retrieve a specific artifact's content |
| `DONE` | local | Termination signal | Structured evaluation result |

### External Tools

`list_directory` and `read_file` are dispatched via `dispatch_external_tool()` to the filesystem MCP container. These let EI verify filesystem outcomes — checking that expected directories exist, files were moved, content is correct.

### Local Artifact Tools

`list_artifacts` and `retrieve_artifact` are shared tools from `mcp/artifact_tools.py`. They operate on a snapshot of the current workflow artifacts, letting EI inspect what specialists produced without relying on message summaries. Any specialist with react_step capability can use these tools via config.yaml permissions.

### DONE Signal

The DONE tool is EI's termination signal. Its schema accepts:

```python
class CompletionEvaluation(BaseModel):
    is_complete: bool           # Whether the task is verified complete
    reasoning: str              # Brief explanation (1-2 sentences)
    missing_elements: str       # What's still needed (empty if complete)
    recommended_specialists: list[str]  # Who should handle missing work
```

When `_routable_specialists` is set (injected by graph_builder), the `recommended_specialists` field gains an enum constraint — the model can only recommend specialists that actually exist in the graph.

---

## Prompt and Context Assembly

### Loading Chain: Config to System Prompt

```
config.yaml
  specialists.exit_interview_specialist.prompt_file: "exit_interview_prompt.md"
  specialists.exit_interview_specialist.llm_config: "model_name_here"
    │
    ▼
GraphBuilder._attach_llm_adapter()
    │
    ├── load_prompt("exit_interview_prompt.md")
    │   reads: APP_ROOT/prompts/exit_interview_prompt.md
    │   returns: system_prompt (str)
    │
    └── AdapterFactory.create_adapter(name, system_prompt)
        stores: self.system_prompt = "<full prompt text>"
```

EI reads these at the top of `_verify()`:

```python
model_id = getattr(self.llm_adapter, 'model_name', "default")
system_prompt = getattr(self.llm_adapter, 'system_prompt', "") or ""
```

### Three Layers of What the Model Sees

**Layer 1: System Prompt** — static identity and behavioral instructions

The full text of [exit_interview_prompt.md](../../app/prompts/exit_interview_prompt.md). This defines:
- EI's identity ("You are the **Exit Interview evaluator**...")
- Available tool categories (filesystem, artifacts, DONE)
- Verification process (follow execution_steps, evaluate against acceptance_criteria)
- DONE protocol (must call tools before DONE)
- Final-state-only constraint (cannot access original or intermediate states)
- Verification principles (check filesystem not messages, be conservative, be specific)

**Layer 2: Task Prompt** — the specific verification context for this invocation

Built by `_build_task_prompt()`:

```
**Original User Request:**
Organize files in /workspace/test into category subfolders based on content

**Success Criteria:**
**Plan Summary:** Verify file organization by category
**Verification Steps:**
  - List /workspace/test to check subdirectories exist
  - Verify no unsorted files remain in root directory
  - Sample a file in each category to confirm content match

**Specialists That Have Executed:**
project_director

**Artifact Keys Available:**
exit_plan, task_plan, user_request

Begin verification. Use tools to check real outcomes, then call DONE.
```

Key data sources:
- `user_request` — from `artifacts["user_request"]` (written by Triage)
- `exit_plan` — from `artifacts["exit_plan"]` (written by SA via MCP, see below)
- `routing_history` — which specialists have executed
- `artifact_keys` — what artifacts are available for inspection

**Layer 3: Trace** — accumulated tool call history within the current verification

Same structure as PD's trace. Each entry records one tool call and its result:

```python
{
    "iteration": 1,
    "tool_call": {"id": "call_2", "name": "list_directory", "args": {"path": "/workspace/test"}},
    "observation": "[DIR] animals\n[DIR] plants\n[FILE] readme.txt",
    "success": True,
}
```

---

## The exit_plan: SA-Generated Verification Criteria

### Lazy Creation via SA MCP (#115, #129)

EI calls SA's `create_plan()` MCP tool on first invocation to produce an `exit_plan`. The plan provides structured verification criteria — without it, EI is verifying against only the raw user request.

```python
# _ensure_exit_plan() — called at the top of _execute_logic
verification_context = (
    f"User request: {user_request}"
    f"\n\nAcceptance criteria: {acceptance_criteria}"     # from task_plan
    f"\n\nGenerate a VERIFICATION PLAN with steps to CHECK..."
)

result = self.mcp_client.call(
    "systems_architect", "create_plan",
    context=verification_context,
    artifact_key="exit_plan",
    available_tools=verification_tools,                   # EI's tool inventory
)
```

The `available_tools` parameter tells SA what EI can actually do, so SA constrains verification steps to EI's capabilities.

### Write-Once, Read-Many

Once created, the exit_plan persists in artifacts across retries. On subsequent EI invocations, `_ensure_exit_plan()` sees the existing plan and skips the SA call.

### How the Prompt Uses exit_plan

The exit_plan's `execution_steps` become EI's verification checklist and `acceptance_criteria` become its definition of done. From the system prompt:

> The task prompt provides **Success Criteria** generated by the Systems Architect. These contain:
> - **execution_steps**: Your verification checklist — follow these step by step using your tools
> - **acceptance_criteria**: The definition of "done" — what the completed end state looks like

### Adapting to Final-State Constraints

SA may generate execution_steps that reference prior state (e.g., "compare file names against the original list"). EI cannot execute these literally because it only sees current state. The system prompt teaches adaptation:

> Some verification steps from the Success Criteria may reference prior state. You cannot execute these literally. Instead, adapt: verify what IS observable from the current state. If the acceptance_criteria says "no files remain in the root directory," you CAN verify that by listing the directory.

---

## Result Builders

Every EI invocation ends via exactly one of three result builders:

| Exit Path | Trigger | `task_is_complete` | Key Artifacts |
|-----------|---------|-------------------|---------------|
| **Complete** | DONE(is_complete=True) after tool use | `True` | `exit_interview_result.is_complete=True` |
| **Incomplete** | DONE(is_complete=False) after tool use | `False` | `exit_interview_result` with `missing_elements`, `recommended_specialists` |
| **Unavailable** | prompt-prix not reachable | `True` | `exit_interview_result.reasoning` = "prompt-prix unavailable" |

### Complete Result

```python
{
    "task_is_complete": True,
    "artifacts": {
        "exit_plan": {...},                    # Persisted for archive
        "exit_interview_result": {
            "is_complete": True,
            "reasoning": "All files organized correctly",
        },
    },
}
```

### Incomplete Result

```python
{
    "task_is_complete": False,
    "artifacts": {
        "exit_plan": {...},
        "exit_interview_result": {
            "is_complete": False,
            "reasoning": "Files have not been sorted yet",
            "missing_elements": "3 files remain unsorted in /workspace/test",
            "recommended_specialists": ["project_director"],
        },
    },
    "scratchpad": {
        "recommended_specialists": ["project_director"],
        "exit_interview_incomplete": True,
    },
}
```

The `recommended_specialists` in scratchpad is read by `after_exit_interview()` for routing decisions. The `exit_interview_result` artifact is read by Facilitator on retry to build "Retry Context" in `gathered_context`.

### Unavailable Result (#195)

When prompt-prix is unreachable, EI returns `task_is_complete=True` with an honest explanation. This is deliberate:

- **Not a degraded evaluation** — a tool-less "evaluation" would produce credible-sounding false negatives (the old single-pass path did exactly this)
- **Not a retry** — infrastructure failure won't fix itself on the next iteration
- **Honest signal** — downstream consumers see the reasoning and know verification was skipped

```python
{
    "task_is_complete": True,
    "artifacts": {
        "exit_interview_result": {
            "is_complete": True,
            "reasoning": "prompt-prix unavailable — cannot verify, defaulting to complete",
        },
    },
}
```

---

## Signal Preservation (#114)

EI does **not** touch `max_iterations_exceeded` in its result artifacts. This flag is set by the executing specialist (e.g., PD) and consumed by Facilitator to detect BENIGN continuation. EI is a bystander — it reads the flag implicitly (via artifacts snapshot for tool dispatch) but never writes it.

If EI cleared the flag, Facilitator couldn't distinguish BENIGN continuation from a correction cycle.

---

## Graph Routing: `after_exit_interview()`

After EI runs, `graph_orchestrator.after_exit_interview()` routes based on the result:

| Condition | Route | Effect |
|-----------|-------|--------|
| `task_is_complete=True` | END | Workflow terminates |
| `task_is_complete=False` + `loop_detected` in scratchpad | END | Abort with `termination_reason` |
| `task_is_complete=False` + `error` cleared | Facilitator | Refresh context, retry |
| `task_is_complete=False` (fallback) | Router | Direct retry (shouldn't happen with Facilitator enabled) |

The loop abort path prevents infinite EI → Facilitator → Router → Specialist → EI cycles. When the graph detects an unproductive loop pattern and EI confirms the task is still incomplete, termination is forced.

---

## #195: What Changed (Architecture Cleanup)

Before #195, EI had two parallel execution engines: a react_step tool loop and a single-pass LLM evaluation fallback. The fallback was the default path in practice — prompt-prix connection timing meant `_has_react_capability()` often returned False.

The single-pass path was a silent failure mode: EI evaluated completion by reading artifact summaries and message content, then produced credible-sounding assessments like "The system has not executed the required verification steps using list_directory" — EI was diagnosing its own inability to use tools as the specialist's failure. This burned iteration budgets on false negatives.

| Before (#195) | After (#195) |
|----------------|-------------|
| ~730 lines with two execution engines | ~320 lines, react_step only |
| `_evaluate_completion()` single-pass LLM path | Removed — no fallback |
| `_has_react_capability()` custom check | `is_react_available()` shared function |
| `_build_artifact_summary()` baked into EI | `mcp/artifact_tools.py` shared module |
| `_build_verification_system_prompt()` in Python | `exit_interview_prompt.md` serves react_step path |
| Module-level `_list_artifacts_tool`/`_browse_artifact_tool` | `artifact_tool_defs()` + `dispatch_artifact_tool()` |
| `_EI_TOOL_PARAMS` mutated at module level | `_build_tool_params()` returns fresh dict |
| Prompt file served single-pass path | Prompt file serves react_step identity/behavior |
| False negatives from tool-less evaluation | Honest "cannot verify" when tools unavailable |

---

## Configuration Reference

### Specialist Registration (config.yaml)

```yaml
specialists:
  exit_interview_specialist:
    type: "llm"
    prompt_file: "exit_interview_prompt.md"
    description: "Gates the END node by validating task completion..."
    excluded_from:
      - triage_architect      # Not recommended by Triage
      - router_specialist      # Not selected by Router
    tools:
      prompt-prix:
        - react_step           # react_step MCP for tool loop
      systems_architect:
        - create_plan          # Lazy exit_plan generation
      filesystem:
        - list_directory       # Verify filesystem state
        - read_file            # Read file contents
```

EI is `excluded_from` both Triage and Router because it's graph-wired, not user-routable. It is invoked automatically by `check_task_completion` and `classify_interrupt`.

### Dependency Injection

- `llm_adapter` — provides `model_name` and `system_prompt` for react_step calls
- `mcp_client` — internal MCP for SA's `create_plan()`
- `external_mcp_client` — external MCP for filesystem and prompt-prix react_step
- `_routable_specialists` — injected by `graph_builder.set_routable_specialists()` for DONE schema enum

---

## Archive Forensics

```bash
# Check if EI ran in routing history
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check exit_interview_result
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.exit_interview_result'

# Check exit_plan (SA-generated verification criteria)
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.exit_plan'

# Check EI's recommended_specialists on incomplete
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.scratchpad.recommended_specialists'

# Check state_timeline for EI's entry
unzip -p ./logs/archive/run_*.zip state_timeline.jsonl | grep exit_interview | jq .
```

**Key things to check:**
- `exit_interview_result` is present and has `reasoning` (not empty)
- On INCOMPLETE, `missing_elements` is specific (names files/dirs, not generic)
- `exit_plan` is present (SA was called successfully)
- EI appears after the executing specialist in `routing_history`
- No `max_iterations_exceeded` in EI's artifacts (it doesn't touch the flag)

---

## Key Files

| File | Purpose |
|------|---------|
| [exit_interview_specialist.py](../../app/src/specialists/exit_interview_specialist.py) | EI implementation — loop, dispatch, SA call, result builders |
| [exit_interview_prompt.md](../../app/prompts/exit_interview_prompt.md) | System prompt — tool descriptions, DONE protocol, final-state constraints |
| [artifact_tools.py](../../app/src/mcp/artifact_tools.py) | Shared artifact inspection tools (list_artifacts, retrieve_artifact) |
| [react_step.py](../../app/src/mcp/react_step.py) | Shared helpers: `ToolDef`, `is_react_available`, `call_react_step`, `build_tool_schemas`, `dispatch_external_tool` |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_task_completion()`, `classify_interrupt()`, `after_exit_interview()` — all EI routing |
| [specialist_categories.py](../../app/src/workflow/specialist_categories.py) | `CORE_INFRASTRUCTURE` (includes EI), `SKIP_EXIT_INTERVIEW` |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Reads `exit_interview_result` on retry to build EI feedback in `gathered_context` |
| [systems_architect.py](../../app/src/specialists/systems_architect.py) | MCP service: `create_plan()` produces `exit_plan` |

---

## Summary

The Exit Interview is a **react_step verification agent** that:

1. Receives `task_is_complete=True` from a specialist or `max_iterations_exceeded` from the interrupt classifier
2. Lazy-creates an `exit_plan` via SA MCP with verification steps tailored to EI's tool capabilities
3. Runs a react_step loop to inspect the filesystem and artifacts using real tools
4. Enforces tool-use-before-DONE (#193) — the model must verify real outcomes before judgment
5. Calls DONE with a structured `CompletionEvaluation` (complete, reasoning, missing elements, recommended specialists)
6. Returns an honest "cannot verify" signal when prompt-prix is unavailable — no degraded evaluation (#195)

EI is a **final-state observer**. It cannot see what was there before, what was moved, or what changed. It verifies that the expected end state exists, adapting SA's verification steps to what is observable in the current filesystem and artifacts.
