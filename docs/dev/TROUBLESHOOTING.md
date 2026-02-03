# Troubleshooting Guide

This guide helps you diagnose issues by analyzing the Atomic Archival Packages (`.zip` files) produced after each workflow run.

---

## Quick Start: My Workflow Failed, Now What?

1. **Find the archive:** `ls -la ./logs/archive/*.zip | tail -5`
2. **Extract manifest:** `unzip -p <archive.zip> manifest.json | jq .`
3. **Check routing_history:** Did the expected specialists run?
4. **Check llm_traces:** `unzip -p <archive.zip> llm_traces.jsonl | jq -s .`
5. **Check final_state:** `unzip -p <archive.zip> final_state.json | jq 'keys'`
6. **Compare traces to routing_history:** All specialists should have corresponding trace entries (see [Trace Types](#trace-types))

---

## Archive File Reference

| File | Purpose | Key Fields |
|------|---------|------------|
| `manifest.json` | Run metadata | `routing_history`, `termination_reason` |
| `llm_traces.jsonl` | Per-LLM-call records | `step`, `specialist`, `from_source`, `tool_calls`, `scratchpad_signals` |
| `final_state.json` | Complete GraphState at termination | `messages`, `artifacts`, `scratchpad`, `routing_history` |
| `report.md` | Human summary | Routing history, **intelligently formatted** artifacts |
| `final_user_response.md` | What user received | Plain text |

### Where Archives Are Produced

Archives are created by the termination chain:
1. **EndSpecialist** ([end_specialist.py](../../app/src/specialists/end_specialist.py)) synthesizes the final response
2. **ArchiverSpecialist** ([archiver_specialist.py](../../app/src/specialists/archiver_specialist.py)) creates the `.zip` package

### report.md Intelligent Formatting

The `report.md` file uses smart formatting for key artifacts (see [state_pruner.py](../../app/src/utils/state_pruner.py)):

| Artifact | Format |
|----------|--------|
| `research_trace_N` | Numbered tool call log with iteration, tool, args summary, result preview |
| `exit_interview_result` | Structured fields: Status, Method, Reasoning, Missing, Recommended |
| `project_context` | Structured fields: State, Summary, Next steps |
| `context_plan`, `system_plan` | Pretty-printed JSON |
| Other dicts/lists | JSON (truncated at 2000 chars) |
| Strings | Code fence (truncated at 5000 chars) |

---

## Trace Types

All specialists now emit traces to `llm_traces.jsonl`. The `specialist_type` field distinguishes them:

| Type | Description | `model_id` |
|------|-------------|------------|
| `llm` | Makes LLM calls | Model name (e.g., `gemini-2.0-flash`) |
| `procedural` | Orchestration/data processing | `no_llm_call` |
| `hybrid` | May or may not call LLM | Varies |

**Note:** Step numbers are now contiguous. All specialists in `routing_history` have corresponding entries in `llm_traces.jsonl`.

---

## Reading llm_traces.jsonl

Each line is a JSON object for one LLM call:

```json
{
  "step": 0,
  "specialist": "triage_architect",
  "from_source": "user",
  "tool_calls": [{"name": "ContextPlan", "args": {...}}],
  "scratchpad_signals": {"recommended_specialists": ["research_orchestrator"]},
  "latency_ms": 7067,
  "model_id": "openai/gpt-oss-20b-gguf/..."
}
```

**Key interpretation:**
- `step` starts at 0, increments per LLM call (not per specialist!)
- `tool_calls` shows structured output (Pydantic models)
- `scratchpad_signals` shows what this specialist told routing
- `from_source` is the previous specialist in routing_history

---

## Common Failure Patterns

### 1. Triage reasoning/actions mismatch

**Symptom:** Triage reasoning says "need web search" but `actions: []` is empty

**Cause:** Open-weights model produced inconsistent structured output

**Diagnosis:**
```bash
unzip -p <archive.zip> llm_traces.jsonl | jq -r 'select(.specialist=="triage_architect") | .tool_calls[0].args'
```

**What to check:**
- Is reasoning consistent with actions?
- Did the model produce the expected action type?

**Related:** [#40](https://github.com/shanevcantwell/langgraph-agentic-scaffold/issues/40)

### 2. Specialist exited early (no LLM call)

**Symptom:** Specialist in routing_history but no corresponding llm_trace entry

**Example:** `routing_history: [triage, research_orchestrator, default_responder]` but only steps 0 and 2 in llm_traces

**Causes:**
- Procedural specialist (doesn't use LLM)
- Specialist precondition failed (missing required artifact)
- Specialist early-exit (missing required input like `research_goal`)

**Diagnosis:** Read the specialist's `_execute_logic` to find early-exit conditions

### 3. Loop detection terminated workflow

**Symptom:** `termination_reason` contains "stuck in an unproductive loop"

**Cause:** Same specialists repeated 3+ times without progress

**Diagnosis:** Check `routing_history` for repeating patterns like `[A, B, A, B, A, B]`

### 4. Wrong specialist selected

**Symptom:** User asked for X, but Y specialist ran

**Diagnosis:**
1. Check Triage's `recommended_specialists` in llm_traces
2. Check Router's llm_trace for its final decision
3. Check Router's prompt (includes specialist descriptions and recommendations)

### 5. Exit Interview retry creates duplicate folders (context starvation)

**Symptom:** Task like "categorize files" creates "Plant", "Plant_new", "AnotherPlant" instead of clean folders

**Cause:** Facilitator was overwriting `gathered_context` on Exit Interview retry instead of accumulating. Specialist saw fresh/confused context, hedged with new folder names.

**The Bug (Issue #96):**
```
project_director (partial work)
    → Exit Interview (INCOMPLETE)
    → Facilitator (OVERWRITES gathered_context)  ← was the bug
    → Router
    → project_director (confused - sees fresh context)
```

**The Fix:** Facilitator now accumulates context (`+=` not `=`). See [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) lines 113, 260-268.

**If this recurs (Phase 2 needed):**
- `gathered_context` accumulation may not be enough for complex tasks
- ReAct loop's internal reasoning isn't preserved between invocations
- May need `reasoning_trace` artifact from react_mixin

**Related:** Issue #96, ADR-ROADMAP-001 Phase 1

### 6. No archive produced (crash/abort)

**Symptom:** Workflow runs for a long time, shows `error_report` in routing, but no new `.zip` appears in `./logs/archive/`

**Diagnosis:**
```bash
# Check timestamps - is there a new archive?
ls -la ./logs/archive/*.zip | tail -5

# Check server log for the actual error
grep -i "error\|exception" ./logs/agentic_server.log | tail -20
```

**Common causes:**

| Error | Log message | Root cause |
|-------|-------------|------------|
| Context overflow | `Context length exceeded` | Accumulated context exceeded model's context window |
| Recursion limit | `GraphRecursionError: Recursion limit of 40` | Too many nodes before loop invariant triggered |
| Crash in error_report | Various | Exception during error handling prevents archive |

**Context overflow fix:** ADR-ROADMAP-001 Phase 3 (Smart Curation) will add context compression. For now, reduce `max_iterations` in config to limit accumulation.

**Recursion limit vs loop invariant:** LangGraph's hard limit (40) may trigger before our soft loop detection (3 repeats). The hard limit causes a crash without archiving.

**Known issue:** UI Abort does not trigger archiver - the workflow simply stops without preserving state.

### 7. ReactEnabledSpecialist missing attribute error

**Symptom:** `AttributeError: 'MySpecialist' object has no attribute '_serialize_for_provider'` (or `_check_stagnation`, `_trace_to_tool_result`, etc.)

**Cause:** When ReAct is enabled via config (`react: enabled: true`), GraphBuilder's `ReactEnabledSpecialist` wrapper injects ReActMixin methods onto the specialist at runtime. If new methods are added to ReActMixin (e.g., for ADR-CORE-055), the injection list must also be updated.

**Diagnosis:**
```bash
# Check the injection list in graph_builder.py
grep -A 15 "methods_to_inject" app/src/workflow/graph_builder.py
```

**Fix:** Ensure `methods_to_inject` in [graph_builder.py](../../app/src/workflow/graph_builder.py) (line ~93) includes all methods called by `execute_with_tools()`:

```python
methods_to_inject = [
    'execute_with_tools',
    '_build_tool_schemas',
    '_execute_tool',
    '_format_tool_result_message',
    '_compute_call_signature',      # Stagnation detection
    '_serialize_for_provider',      # ADR-CORE-055: trace-based serialization
    '_check_stagnation',            # ADR-CORE-055: cycle detection
    '_trace_to_tool_result',        # ADR-CORE-055: trace conversion
]
```

Also check class attributes are injected (line ~109):
```python
attributes_to_inject = [
    'CYCLE_MIN_REPETITIONS',  # Stagnation threshold
    'TOOL_PARAMETERS',        # MCP tool schema cache
    'EXTERNAL_MCP_SERVICES',  # External MCP service list
]
```

**Related:** ADR-CORE-055 (trace-based ReAct serialization)

---

### 8. Specialist loops unexpectedly

**Symptom:** Specialist runs, produces output, but workflow keeps looping instead of completing

**This is NOT a bug.** Per ADR-CORE-036 (Exit Interview Pattern):
- Specialists do NOT decide completion
- Exit Interview evaluates whether the task is done
- If looping continues, Exit Interview said INCOMPLETE

**Diagnosis:**
```bash
unzip -p $ARCHIVE final_state.json | jq '.artifacts.exit_interview_result'
```

Check `is_complete`, `reasoning`, and `missing_elements` to understand why Exit Interview said INCOMPLETE.

**Common causes:**
- Exit Interview can't verify filesystem state (Issue #97) - it only sees artifact keys
- Specialist produced artifact but Exit Interview thinks more work needed
- Missing elements identified but no specialist can address them

**Related:** ADR-CORE-036, ADR-CORE-058 (Phase 2 verification orchestrator)

---

## Code Paths for Deep Investigation

| Symptom | Start Here |
|---------|------------|
| Routing decisions | [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) - decider functions |
| Which specialists loaded | [graph_builder.py](../../app/src/workflow/graph_builder.py) - `_load_and_configure_specialists()` |
| Specialist preconditions | [node_executor.py](../../app/src/workflow/executors/node_executor.py) - `create_safe_executor()` |
| Archive production | [archiver_specialist.py](../../app/src/specialists/archiver_specialist.py) - `_create_atomic_package()` |
| Subgraph wiring | [workflow/subgraphs/](../../app/src/workflow/subgraphs/) - individual subgraph files |

---

## Bash One-Liners

```bash
# List recent archives
ls -la ./logs/archive/*.zip | tail -10

# Extract and pretty-print manifest
unzip -p ./logs/archive/<archive.zip> manifest.json | jq .

# Show all LLM traces as array
unzip -p ./logs/archive/<archive.zip> llm_traces.jsonl | jq -s .

# Get routing history as arrow-separated string
unzip -p ./logs/archive/<archive.zip> manifest.json | jq -r '.routing_history | join(" → ")'

# Find triage's recommended specialists
unzip -p ./logs/archive/<archive.zip> llm_traces.jsonl | jq -r 'select(.specialist=="triage_architect") | .scratchpad_signals.recommended_specialists'

# Check termination reason
unzip -p ./logs/archive/<archive.zip> manifest.json | jq -r '.termination_reason'

# Show all specialists that ran with their step numbers
unzip -p ./logs/archive/<archive.zip> llm_traces.jsonl | jq -r '[.step, .specialist] | @tsv'

# Show final_state keys (what's in the state at termination)
unzip -p ./logs/archive/<archive.zip> final_state.json | jq 'keys'

# Show all artifact keys at workflow end
unzip -p ./logs/archive/<archive.zip> final_state.json | jq '.artifacts | keys'

# Show scratchpad signals (inter-specialist communication)
unzip -p ./logs/archive/<archive.zip> final_state.json | jq '.scratchpad'
```

---

## Context Engineering Flow

Understanding how context flows through the system is critical for debugging "specialist didn't have the right context" issues.

### The Flow

```
User Request
    ↓
TriageArchitect → Creates ContextPlan (actions + recommended_specialists)
    ↓
Facilitator → Executes actions, produces gathered_context artifact
    ↓
Router → Sees gathered_context, routes to specialist
    ↓
Specialist → Receives context via _get_enriched_messages()
```

### Key Mechanism: `_get_enriched_messages()`

All specialists that need context call `self._get_enriched_messages(state)` (defined in [base.py:45-79](../../app/src/specialists/base.py#L45-L79)). This method:

1. Gets messages from state
2. Checks for `gathered_context` artifact
3. If present, appends it as a HumanMessage: `[Context gathered by the system]:\n\n{gathered_context}`

**To verify context injection:** Check if specialist uses `_get_enriched_messages()` vs raw `state["messages"]`.

### Debugging Context Issues

```bash
# Check what ContextPlan Triage created
unzip -p <archive.zip> llm_traces.jsonl | jq -r 'select(.specialist=="triage_architect") | .tool_calls[0].args'

# Check what Facilitator gathered
unzip -p <archive.zip> final_state.json | jq '.artifacts.gathered_context'

# Check if gathered_context is present (non-null)
unzip -p <archive.zip> final_state.json | jq '.artifacts | has("gathered_context")'
```

**Deep dive:** See [FACILITATOR.md](../specialist_profiles/FACILITATOR.md) for complete details on context gathering.

---

## Exit Interview & Facilitator Roadmap (ADR-ROADMAP-001)

The Exit Interview pattern validates task completion before allowing termination. See [ADR-ROADMAP-001](../ADRs/proposed/ADR-ROADMAP-001_Facilitator_Evolution.md) for the full design.

### Implementation Status

| Phase | Feature | Status | Notes |
|-------|---------|--------|-------|
| 1 | Exit Interview gates END | ✅ Done | LLM evaluates completion |
| 1 | Heuristic early-exit | ✅ Done | `max_iterations_exceeded` triggers INCOMPLETE |
| 1 | ReturnControlMode | ✅ Done | ACCUMULATE/RESET modes (#102) |
| 1 | Feedback surfacing | ✅ Done | `exit_interview_result` in gathered_context (#100) |
| 1 | max_iterations flag clearing | ✅ Done | Flag consumed after Exit Interview (#104) |
| 2 | Structured retry output | Pending | CompletionResult for external agents |
| 3 | Smart curation | Pending | Weight-based context compression |

### Current Test: Categorize Files

**Test task:** Read files in `categories_test/`, create category folders, copy files to appropriate folders.

**Reading traces:** See [TRACE_READING_GUIDE.md](../tests/TRACE_READING_GUIDE.md) for how to analyze archive packages.

**Quick trace check:**
```bash
ARCHIVE=$(ls -t ./logs/archive/*.zip | head -1)
unzip -p $ARCHIVE report.md
```

**What to look for in `research_trace_0`:**
- `read_file` / `list_directory` = gathering info
- `copy_file` / `create_directory` = doing the work
- If only reads and no copies → project_director stopped prematurely

---

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture overview
- [SPECIALISTS.md](SPECIALISTS.md) - How specialists work
- [SUBGRAPHS.md](SUBGRAPHS.md) - Graph construction and edge wiring
- [CONFIGURATION_GUIDE.md](../CONFIGURATION_GUIDE.md) - 3-tier configuration system
- [FACILITATOR.md](../specialist_profiles/FACILITATOR.md) - Context gathering specialist profile
