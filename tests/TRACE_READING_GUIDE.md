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
- All artifacts with contents (including `research_trace_0`)
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

**IMPORTANT:** The `llm_traces.jsonl` entry for project_director shows `tool_calls: []` because ReAct specialists record their work differently. Look at the **artifacts** instead:

```bash
# The actual tool calls are in resume_trace (single accumulated trace)
unzip -p $ARCHIVE final_state.json | jq '.artifacts.resume_trace'

# Did it claim complete? What state?
unzip -p $ARCHIVE final_state.json | jq '.artifacts.project_context'

# How many iterations used?
unzip -p $ARCHIVE final_state.json | jq '.artifacts.iterations_used'
```

## Step 3: What Tools Were Called?

```bash
# List all tools called with their arguments
unzip -p $ARCHIVE final_state.json | jq '.artifacts.resume_trace[] | {iteration, tool_call}'
```

**For categorize test, look for:**
- `read_file` - reading file contents ✓
- `list_directory` - listing folders ✓
- `create_directory` - creating category folders (THIS IS PROGRESS)
- `move_file` - actually moving files (THIS IS THE WORK)

If only reads, no moves → project_director stopped too early.

## Step 3a: Concurrent Batch Analysis

Since Phase 0.9, PD can return multiple tool calls per response. These execute concurrently via `ThreadPoolExecutor` and share the same `iteration` number in the trace. Use the script's `concurrency` command:

```bash
python scripts/analyze_archive.py $ARCHIVE concurrency
```

Example output:
```
=== research_trace_0 (16 tool calls) ===
  iter  0: list_directory, read_file, read_file, read_file, read_file, read_file, read_file  <-- CONCURRENT (7)
  iter  1: create_directory, create_directory, create_directory, move_file, move_file, move_file  <-- CONCURRENT (6)
  ---
  2 iterations: 2 concurrent, 0 sequential (max batch: 7)
```

**How to read it:**
- Each line is one iteration (one LLM response → one or more tool calls)
- `<-- CONCURRENT (N)` means N tools dispatched in parallel from a single response
- Lines without the marker are sequential (single tool call per response)
- `iter -1` entries indicate a resume trace deserialization bug — the iteration wasn't set on re-hydration

**What to look for:**
- Good: reads batched together, then creates+moves batched together (model is efficient)
- Bad: single sequential calls when independence is obvious (model not using concurrency)
- Suspicious: `DONE` mixed with other tools in same batch (DONE takes priority, others are discarded)

**Trace field reference:** Entries use `tool` (not `tool_name`). The iteration number comes from `iteration` field. Both are in `research_trace_N` within `final_state.json → artifacts`.

## Step 4: Exit Interview Evaluation

```bash
# What did Exit Interview decide?
unzip -p $ARCHIVE final_state.json | jq '.artifacts.exit_interview_result'

# Was max_iterations_exceeded set?
unzip -p $ARCHIVE final_state.json | jq '.artifacts.max_iterations_exceeded'
```

## Step 5: Check for Errors

```bash
# Any errors in scratchpad?
unzip -p $ARCHIVE final_state.json | jq '.scratchpad.error'

# Detailed error report?
unzip -p $ARCHIVE final_state.json | jq -r '.scratchpad.error_report'
```

## Key Questions for Categorize Test

1. **Did project_director call move_file?** → Check `resume_trace` for tool_call.name="move_file"
2. **Why did it stop?** → Check `iterations_used` vs max_iterations, check `project_context.state`
3. **Did Exit Interview catch the incomplete work?** → Check `exit_interview_result.is_complete`
4. **Was there a retry?** → Count `project_director` in routing_history; all invocations share one `resume_trace`
5. **How many PD invocations?** → Count `project_director` in routing_history

## Expected Happy Path

```
triage_architect → facilitator_specialist → router_specialist → project_director
    (reads files, creates folders, copies files, sets state="complete")
→ router_specialist → exit_interview_specialist
    (verifies files are in category folders)
→ end_specialist
```

## Common Failure Modes

| Symptom | Check | Root Cause |
|---------|-------|------------|
| Loop: router → systems_architect | project_context.state | project_director stopped early |
| Loop: router → project_director | research_trace_N | Specialist not making progress |
| Premature END | exit_interview_result | LLM parse failure defaulted to complete |
| max_iterations sticky | artifacts.max_iterations_exceeded | Old bug - should be False after Exit Interview |
| iter -1 in trace | `concurrency` command | Resume trace deserialization doesn't set iteration |
| All sequential (no batches) | `concurrency` command | Model not returning `actions` array or adapter fallback to singular `action` |

---

## Successful Run Analysis (2026-02-05)

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
3. **resume_trace shows accumulated history** - duplicate iteration numbers (0,1,2,0,1,2) indicate trace concatenation from multiple runs
4. **research_trace_2 has the actual work** - 20 tool calls including create_directory and move_file
5. **Triage reasoning truncated** - ended mid-sentence at "But the instruction says " (model output limit)

### Tool Call Progression

| Trace | Tool Calls | What Happened |
|-------|------------|---------------|
| research_trace_1 | 3 | Listed dir, read 2 files, stopped |
| research_trace_2 | 20 | Read all 6 files, created 3 dirs, moved all 6 files |

### Context Flow
- `gathered_context` surfaced EI feedback: "Need to read each file..."
- `exit_plan` was empty `{}` - SA MCP call may have failed
- Final EI verified: "leaving the original directory empty; verification of the new subfolders confirms"

### Key Insight: move_file not copy_file
The task uses `move_file`, not `copy_file`. Update Step 3 accordingly.
