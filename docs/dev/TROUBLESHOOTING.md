# Troubleshooting Guide

This guide helps you diagnose issues by analyzing the Atomic Archival Packages (`.zip` files) produced after each workflow run.

---

## Quick Start: My Workflow Failed, Now What?

1. **Find the archive:** `ls -la ./logs/archive/*.zip | tail -5`
2. **Extract manifest:** `unzip -p <archive.zip> manifest.json | jq .`
3. **Check routing_history:** Did the expected specialists run?
4. **Check llm_traces:** `unzip -p <archive.zip> llm_traces.jsonl | jq -s .`
5. **Check final_state:** `unzip -p <archive.zip> final_state.json | jq 'keys'`
6. **Look for gaps:** Missing steps indicate procedural specialists (see [Known Observability Gaps](#known-observability-gaps))

---

## Archive File Reference

| File | Purpose | Key Fields |
|------|---------|------------|
| `manifest.json` | Run metadata | `routing_history`, `termination_reason` |
| `llm_traces.jsonl` | Per-LLM-call records | `step`, `specialist`, `from_source`, `tool_calls`, `scratchpad_signals` |
| `final_state.json` | Complete GraphState at termination | `messages`, `artifacts`, `scratchpad`, `routing_history` |
| `report.md` | Human summary | Routing history, artifacts, conversation |
| `final_user_response.md` | What user received | Plain text |

### Where Archives Are Produced

Archives are created by the termination chain:
1. **EndSpecialist** ([end_specialist.py](../../app/src/specialists/end_specialist.py)) synthesizes the final response
2. **ArchiverSpecialist** ([archiver_specialist.py](../../app/src/specialists/archiver_specialist.py)) creates the `.zip` package

---

## Known Observability Gaps

**These are documented limitations - not bugs you're imagining:**

| Gap | Explanation |
|-----|-------------|
| Procedural specialists have no llm_trace | They don't call LLMs. Check routing_history - they DID run. |
| Step numbers have gaps | Gaps = specialists that didn't call LLM (procedural or deterministic routing) |

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

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture overview
- [SPECIALISTS.md](SPECIALISTS.md) - How specialists work
- [SUBGRAPHS.md](SUBGRAPHS.md) - Graph construction and edge wiring
- [CONFIGURATION_GUIDE.md](../CONFIGURATION_GUIDE.md) - 3-tier configuration system
