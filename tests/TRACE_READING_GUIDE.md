# Trace Reading Guide for Categorize Test

## Quick Start: Find Latest Archive

```bash
ls -la ./logs/archive/*.zip | tail -3
ARCHIVE="./logs/archive/run_YYYYMMDD_HHMMSS_XXXXXXXX.zip"
```

HH is in GMT from LAS. User is in Mountain.

## Preferred: Python Script

**Use `scripts/analyze_archive.py` instead of manual unzip/jq commands.**

```bash
# Summary (routing, artifacts, tool counts)
python scripts/analyze_archive.py ./logs/archive/run_*.zip

# Show LLM traces with tool calls
python scripts/analyze_archive.py $ARCHIVE traces

# Count tool calls by type (catches missing move_file/create_directory)
python scripts/analyze_archive.py $ARCHIVE tools

# Show concurrent batch analysis (iteration grouping, batch sizes)
python scripts/analyze_archive.py $ARCHIVE concurrency

# Show full prompt for a specific step (e.g., Router = step 1)
python scripts/analyze_archive.py $ARCHIVE prompt 1

# Compare two archives
python scripts/analyze_archive.py $ARCHIVE compare ./logs/archive/other_run.zip

# Show Exit Interview details
python scripts/analyze_archive.py $ARCHIVE ei
```

The script handles glob patterns (`run_*.zip` → uses most recent match) and presents data cleanly without jq gymnastics.

---

## Step 0: Read report.md First

**Start here.** The `report.md` file is a human-readable summary with everything you need:

```bash
unzip -p $ARCHIVE report.md
```

Contains:
- Routing history
- All artifacts with contents (including `completion_signal`)
- `exit_interview_result`
- Final user response

Only use the jq commands below if you need to dig deeper.

---

## Step 1: Routing History & Termination

```bash
# What specialists ran, in order?
unzip -p $ARCHIVE manifest.json | jq -r '.routing_history | join(" → ")'

# Why did it terminate?
unzip -p $ARCHIVE manifest.json | jq -r '.termination_reason'
```

## Step 2: What Did project_director Actually Do?

**IMPORTANT:** The `llm_traces.jsonl` entry for project_director shows `tool_calls: []` because ReAct specialists record their work differently. Look at the **scratchpad** and **artifacts**:

```bash
# Completion signal — the structured exit status (COMPLETED/PARTIAL/BLOCKED/ERROR)
unzip -p $ARCHIVE final_state.json | jq '.artifacts.completion_signal'

# Human-readable summary of what PD actually did
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.specialist_activity'

# Tool-by-tool ReAct log (each entry: tool_call, iteration, observation, success)
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.react_trace'
```

> **Renamed fields (post-#225):** `resume_trace` → `react_trace` (now in scratchpad, not artifacts). `project_context` and `research_trace_N` were removed. `iterations_used` replaced by `completion_signal.status` (PARTIAL = hit max_iterations).

## Step 3: What Tools Were Called?

```bash
# List all tools called with their arguments
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.react_trace[] | {iteration, tool_call}'
```

**Tool progression signals health:**
- `read_file` → `list_directory` → `create_directory` → `move_file` = healthy progression
- Repeated identical calls = stagnation precursor (3+ triggers PATHOLOGICAL signal)
- Only reads, no writes → PD stopped too early

## Step 3a: Concurrent Batch Analysis

Since Phase 0.9, PD can return multiple tool calls per response. These execute concurrently via `ThreadPoolExecutor` and share the same `iteration` number in the trace. Use the script's `concurrency` command:

```bash
python scripts/analyze_archive.py $ARCHIVE concurrency
```

Example output:
```
=== react_trace (16 tool calls) ===
  iter  0: list_directory, read_file, read_file, read_file, read_file, read_file, read_file  <-- CONCURRENT (7)
  iter  1: create_directory, create_directory, create_directory, move_file, move_file, move_file  <-- CONCURRENT (6)
  ---
  2 iterations: 2 concurrent, 0 sequential (max batch: 7)
```

**How to read it:**
- Each line is one iteration (one LLM response → one or more tool calls)
- `<-- CONCURRENT (N)` means N tools dispatched in parallel from a single response
- Lines without the marker are sequential (single tool call per response)

**What to look for:**
- Good: reads batched together, then creates+moves batched together (model is efficient)
- Bad: single sequential calls when independence is obvious (model not using concurrency)
- Suspicious: `DONE` mixed with other tools in same batch (DONE takes priority, others are discarded)

**Trace field reference:** Entries use `tool_call.name` (not `tool_name`). The iteration number comes from `iteration` field. Both are in `scratchpad.react_trace` within `final_state.json`. Each PD invocation gets a fresh trace (#170).

## Step 4: Exit Interview Evaluation

```bash
# What did Exit Interview decide?
unzip -p $ARCHIVE final_state.json | jq '.artifacts.exit_interview_result'

# What signal did PD send? (COMPLETED/PARTIAL/BLOCKED/ERROR)
unzip -p $ARCHIVE final_state.json | jq '.artifacts.completion_signal'
```

**Post-#225 signal fast-path:** If `completion_signal` exists, EI reads it directly (0ms, no LLM call). COMPLETED → accept, PARTIAL → retry, BLOCKED/ERROR → abort with termination_reason. If no signal, EI falls through to legacy verification chain (SA MCP + react_step).

## Step 5: Check for Errors

```bash
# Any errors in scratchpad?
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.error'

# Detailed error report?
unzip -p $ARCHIVE final_state.json | jq -r '.scratchpad.error_report'
```

## Key Diagnostic Questions

1. **Did PD complete the work?** → `artifacts.completion_signal.status` — COMPLETED/PARTIAL/BLOCKED/ERROR
2. **What tools did PD call?** → `scratchpad.react_trace` — look for tool progression, not just presence
3. **Why did PD stop?** → `completion_signal.status`: PARTIAL = max_iterations, BLOCKED = stagnation, ERROR = exception
4. **Did EI use fast-path or legacy?** → EI at 0ms = signal fast-path. >0ms = legacy verification chain.
5. **Was there a retry?** → Count `project_director` in routing_history; each invocation gets a fresh `react_trace` (#170)
6. **How many PD invocations?** → Count `project_director` in routing_history

## Expected Happy Path (post-#225)

```
triage_architect → systems_architect → facilitator_specialist → router_specialist → project_director
    (ReAct tool loop, writes completion_signal={status: COMPLETED, summary: ...})
→ signal_processor_specialist → exit_interview_specialist
    (reads completion_signal, 0ms fast-path accept)
→ end_specialist
```

7 steps, one PD run, EI at 0ms. If you see more steps, check for retry cycles (PD appearing multiple times in routing_history).

## Common Failure Modes

| Symptom | Check | Root Cause |
|---------|-------|------------|
| Loop: router → PD → EI → router → PD | routing_history, completion_signal | PD says COMPLETED but EI can't verify (death spiral) |
| PD stagnation | react_trace (3+ identical tool signatures) | Model stuck in loop, PATHOLOGICAL signal fires |
| PD PARTIAL exit | completion_signal.status = PARTIAL | Hit max_iterations without finishing |
| EI legacy fallback | EI >0ms with react_step calls | completion_signal absent — PD exit path didn't write it |
| Premature END | exit_interview_result | LLM parse failure defaulted to complete |
| Harmony tokens in output | completion_signal.summary | gpt-oss model leaked control tokens through prompt-prix |
| All sequential (no batches) | `concurrency` command | Model not returning `actions` array or adapter fallback to singular `action` |

---

## Successful Run Analysis (2026-02-05, pre-#225)

> **Note:** This analysis predates #225. Field names have changed: `resume_trace` → `react_trace` (now in scratchpad), `research_trace_N` → removed (single `react_trace` per invocation), `project_context` → removed (replaced by `completion_signal`). The routing flow is also different — post-#225 includes SignalProcessor and uses completion_signal fast-path.

**Archive:** `run_20260205_125428_0029452b.zip`

### Routing History
```
triage → router → systems_architect → exit_interview (INCOMPLETE)
    → facilitator → router → project_director → exit_interview (INCOMPLETE)
    → facilitator → router → project_director → exit_interview (INCOMPLETE)
    → facilitator → router → project_director → exit_interview (COMPLETE)
```

### Observations

1. **3 PD invocations - good for 12GB model** - correctly identified Animals/Fruits/Colors categories
2. **EI correctly caught incomplete work twice** - verified by `exit_interview_result.is_complete: false`
3. **Pre-#225 trace accumulated across invocations** — post-#225, each PD invocation gets a fresh `react_trace` (#170)
4. **Triage reasoning truncated** - ended mid-sentence at "But the instruction says " (model output limit)

### Context Flow
- `gathered_context` surfaced EI feedback: "Need to read each file..."
- `exit_plan` was empty `{}` - SA MCP call may have failed
- Final EI verified: "leaving the original directory empty; verification of the new subfolders confirms"
