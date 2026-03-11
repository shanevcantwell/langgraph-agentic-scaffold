# ADR-CORE-076: Data Flow Primitives

**Status:** Implemented (2026-02-17). write_artifact tool, captured_artifacts propagation, signals field.
**Date:** 2026-02-16 (proposed), 2026-02-17 (accepted + implemented)
**Relates to:** ADR-071 (Context Write Permissions), ADR-073 (SafeExecutor Observability), ADR-074 (Summarizer Batch), ADR-ROADMAP-001 (Facilitator Evolution), #170 (resume_trace elimination), #174 (Artifact MCP tools)

## Context

Two weeks of work established the **agent activation flow**: SA entry point (#171), Triage ACCEPT/REJECT (#199), Facilitator always runs (#197), EI completion verification (#193), BENIGN continuation handling (#114). The "when and why does each specialist fire" question is largely answered.

The **data flow architecture** — how information moves between specialists across passes — has not been designed. Individual primitives exist but aren't composed into a coherent system. This ADR inventories the existing primitives, identifies gaps, and frames the design space.

### The "Jazz in the Rests" Problem

PD's `_summarize_activity()` captures only filesystem mutations:
- `create_directory`, `move_file`, `write_file`, `run_command` successes

What it filters out:
- `read_file` results — PD reads 13 files, learns their content, categorizes them. None of that knowledge survives.
- `list_directory` results — PD surveys the workspace but the survey is discarded.
- Failed operations — permission denied errors silently dropped (`if not step.get("success"): continue`).
- Categorization reasoning — PD decides "1.txt is about dolphins → animals" but only the `move_file` persists.

On retry, PD is amnesiac about *why* it acted. It knows it moved files but not what drove those decisions. The observations and reasoning — the "rests" — are where PD's understanding lives.

### The `resume_trace` Lineage

Each evolution got lighter, each solved a symptom:

| Stage | Mechanism | Problem Solved | New Problem Created |
|---|---|---|---|
| `research_trace_N` | Stringly-typed numbered traces in artifacts | Trace persistence | Duplication, naming collisions (#122, #163) |
| `resume_trace` | Single trace blob in graph state | Dedup | State bloat, stale traces bleeding across specialists (0ece3b0, 15 commits, 11 issues) |
| `specialist_activity` | Summary in scratchpad (PD-only) | Lightweight, no state bloat | Last-writer-wins via ior, only captures mutations |
| `accumulated_work` | Facilitator accumulates activity in artifact | Cross-pass persistence | Generic name, flat list, still only captures mutations |
| **`write_artifact`** | **Mid-execution artifact persistence** | **Observations, decisions, reasoning survive** | **Open: naming, curation, WRITABLE_ARTIFACTS enforcement** |

The underlying gap — **specialists can observe but not persist observations** — is now closed by `write_artifact`.

## Existing Primitives Inventory

### Read-path tools (artifact inspection)

| Tool | Location | Consumer | Notes |
|---|---|---|---|
| `list_artifacts(artifacts)` | `mcp/artifact_tools.py` | EI, PD | Returns keys with type/size hints |
| `retrieve_artifact(artifacts, key)` | `mcp/artifact_tools.py` | EI, PD | Full content, no truncation (#183) |
| `dispatch_artifact_tool()` | `mcp/artifact_tools.py` | EI, PD | Local dispatch on mutable snapshot |

### Write-path (specialist → state)

| Mechanism | Location | Consumer | Notes |
|---|---|---|---|
| `write_artifact(artifacts, content, key?)` | `mcp/artifact_tools.py` | PD (via react_step) | **New.** Mid-execution persistence. Optional key with collision resolution. |
| Specialist return dict | All specialists | LangGraph ior merge | Entire react loop must complete. `write_artifact` uses this — snapshot propagates on return. |
| `specialist_activity` | PD's `_summarize_activity()` | Facilitator reads from scratchpad | PD-only. Only mutations. Lightweight summary for curation. |
| `accumulated_work` | `facilitator_specialist.py` | Facilitator accumulates across passes | PD-only source. Flat list in artifact. |

### Dependency declarations (config)

| Config key | Location | Consumer | Status |
|---|---|---|---|
| `requires_artifacts` | config.yaml | NodeExecutor (lines 70-132) | **Functional.** Blocks execution, sets `forbidden_specialists`. Only `summarizer_specialist` uses it. |
| `artifact_providers` | config.yaml | NodeExecutor → `recommended_specialists` | **Dead code.** Leave dead; derive from runtime observation later if needed. |

### Routing signals (scratchpad)

| Signal | Set by | Consumed by | Notes |
|---|---|---|---|
| `forbidden_specialists` | NodeExecutor (dependency block), InvariantMonitor (loop), ImageSpecialist (self-exclusion) | Router `_get_available_specialists()` | Hard constraint — removed from menu |
| `recommended_specialists` | NodeExecutor (would come from `artifact_providers`), Triage | Router `_get_llm_choice()` | Soft hint. Single target = deterministic routing bypass. |
| `decline_task` | `create_decline_response()` (helpers.py) | Router | Specialist self-cancellation at runtime |

### Context delivery

| Mechanism | Owner | Pattern |
|---|---|---|
| `gathered_context` | Facilitator (exclusive write, ADR-071) | ISO-9000: specialists are context-agnostic, Facilitator curates delivery |
| `_get_enriched_messages()` | BaseSpecialist | Injects `gathered_context` into LLM input as system context |

## Implementation: `write_artifact`

```python
def write_artifact(artifacts: dict, content: str, key: str = "") -> str
```

Lets a specialist persist observations, decisions, or intermediate results mid-react-loop.

**Key is optional.** The model can suggest a name, but the system handles naming procedurally:
- If `key` provided and no collision → use it as-is
- If `key` provided but collides → append numeric suffix (`notes` → `notes-2`)
- If `key` omitted → generate a random `adjective-noun-suffix` name (e.g., `wibbly-platypus-glitter`)
- **Return value always includes the actual assigned key** so the model can retrieve later

Auto-naming uses random word-word-word generation (Phase 1). ADR-074 enables a future Phase 2 where lfm2 batch summarizer generates semantically-aligned labels from the content.

### How it works

1. PD snapshots `captured_artifacts = artifacts.copy()` before the react loop
2. `write_artifact` mutates the snapshot dict in place
3. Subsequent `list_artifacts` / `retrieve_artifact` calls see the writes immediately (same dict reference)
4. When PD returns, `captured_artifacts` propagates via result dict → LangGraph ior merge
5. **Critical fix:** `_build_partial_result()` now includes `captured_artifacts` in its return. Written artifacts survive max_iterations — exactly the scenario where they're most valuable.

All four PD result builders (`_build_success_result`, `_build_error_result`, `_build_stagnation_result`, `_build_partial_result`) propagate `captured_artifacts`.

### What models could write

With `write_artifact` available and no prompt guidance (Phase 1: observe first), models gain agency to decide what's worth remembering:

- **Categorization plans:** `write_artifact(content="1.txt→animals (dolphins), 2.txt→music ...", key="categorization_plan")`
- **File content summaries:** `write_artifact(content="1.txt: 200 words about marine dolphins...")`
- **Decision rationale:** `write_artifact(content="Merged 'ocean' and 'marine' into 'animals'", key="decisions")`
- **Progress checkpoints:** `write_artifact(content="8 of 13 files categorized. Remaining: 6, 7, 9, 11, 13")`

## Resolved Design Decisions

| Question | Resolution | Rationale |
|---|---|---|
| 1. Namespacing | No prefix enforcement. Free-form names. | `WRITABLE_ARTIFACTS` (ADR-071 Phase 2) is the stronger runtime mechanism. Prefixes are a naming convention requiring discipline; WRITABLE_ARTIFACTS is a runtime check requiring code changes to bypass. |
| 2. WRITABLE_ARTIFACTS interaction | Validate at SafeExecutor boundary on state merge, not mid-loop. | Unauthorized keys stripped and logged, not crashed. Matches existing pattern: specialists do what they want internally, state merge is gated. |
| 3. Facilitator's role | Two-channel model: Facilitator curates gathered_context (Channel 1), specialists discover via artifact tools (Channel 2). | ISO-9000 still holds for Channel 1. Channel 2 is additive — gives specialists ability to pull detail that Facilitator's curation compressed away. Prompt frames artifact tools as supplementary, not replacement. |
| 4. accumulated_work redundancy | Keep both. Different audiences, different granularity. | `accumulated_work` = lightweight summary for Facilitator curation. Written artifacts = full observations for specialist consumption on retry. |
| 5. artifact_providers | Leave dead. | Derive from runtime observation later if needed. Router's LLM can figure out routing without static dependency hints. |
| 6. Multi-specialist chains | Enabled naturally via Channel 2 (artifact tool discovery). | No Facilitator curation needed for structured inter-specialist data flow. PD writes observations, TA writes analysis, PD discovers TA's analysis via list_artifacts on retry. |

### Two-Channel Data Flow Model

```
Channel 1: Facilitator → gathered_context → specialist prompt
  What the model SEES in its context window before reasoning.
  Curated, compressed, shaped for the task.
  Facilitator's editorial judgment about what matters.

Channel 2: Artifact tools → direct discovery during execution
  What the model ACTIVELY RETRIEVES when it needs specific detail.
  Full fidelity, on demand, the model's own judgment about what to look up.
```

Both channels coexist. Channel 2 is additive to Channel 1, not a replacement.

## Key Files

| File | Role |
|---|---|
| `app/src/mcp/artifact_tools.py` | `write_artifact`, name generation, collision resolution, dispatch |
| `app/src/mcp/__init__.py` | Exports `write_artifact` |
| `app/src/specialists/project_director.py` | Artifact tools wired: `captured_artifacts` snapshot, `_dispatch_tool_call` routing, all result builders propagate |
| `app/src/specialists/exit_interview_specialist.py` | Reference implementation (artifact tools consumer, read-only) |
| `app/src/specialists/facilitator_specialist.py` | `_accumulate_prior_work()`, `_build_task_context()`, `_build_prior_work_section()` |
| `app/src/workflow/executors/node_executor.py` | `requires_artifacts` / `artifact_providers` checking |
| `app/tests/unit/test_artifact_tools.py` | Tests: write, collision, name generation, dispatch |
| `app/tests/unit/test_project_director.py` | Tests: all 4 result builders propagate captured_artifacts |

## What This Does NOT Include

- **WRITABLE_ARTIFACTS enforcement** — ADR-071 Phase 2, separate PR
- **Prompt guidance for PD** — observe what models write first with zero guidance
- **Facilitator curation of written artifacts** — Channel 2 is additive, no Facilitator changes needed
- **Semantic artifact naming** — ADR-074 (lfm2 batch) enables content-aware labels later
- **artifact_providers config wiring** — staying dead per design decision

## Decision

Accepted and implemented. Phase 1 scope:
1. `write_artifact(artifacts, content, key?)` added to `mcp/artifact_tools.py`
2. Artifact tools (read + write) wired into PD following EI pattern
3. All PD result builders propagate `captured_artifacts` — writes survive max_iterations
4. 889 unit tests pass, 0 regressions

Next: observe what models write with the tool available. Let observed behavior inform WRITABLE_ARTIFACTS enforcement, Facilitator curation evolution, and semantic naming.
