# ADR-CORE-077: Signal Processor Architecture

**Status:** Implemented (2026-02-18, commit 1f93bcc). SignalProcessorSpecialist, signals GraphState field with replace reducer, route_from_signal edge function. 893 tests passing.
**Date:** 2026-02-17 (proposed)
**Relates to:** ADR-071 (Context Write Permissions), ADR-072 (Completion Signal Protocol), ADR-073 (SafeExecutor Observability), ADR-076 (Data Flow Primitives), #188 (stale scratchpad flags), #146 (classify_interrupt routing), #200 (implementation issue)

## Context

### The Stagnation Bug

PD's `_build_stagnation_result()` writes `stagnation_detected: True` to **artifacts** (`project_director.py:429`). `classify_interrupt()` reads from **scratchpad** (`graph_orchestrator.py:507`). These are different state dicts with no cross-reference — PATHOLOGICAL stagnation routing **never triggers**. Stagnation is misclassified as normal completion and routed to EI.

This isn't an isolated wiring mistake. It's a symptom of a systemic design gap.

### The Signal Audit

A full audit of routing signals reveals three consumption patterns:

**Consume-and-clear (working correctly):**

| Signal | Reader | Clearing mechanism |
|---|---|---|
| `loop_detected` | `after_exit_interview()` | `scratchpad.pop()` |
| `max_iterations_exceeded` | `classify_interrupt()` routes; Facilitator clears | `False` in Facilitator return |
| `forbidden_specialists` | Router reads; SafeExecutor clears | `None` after successful execution |

**Read-for-routing, never cleared (broken):**

| Signal | Reader | Problem |
|---|---|---|
| `stagnation_detected` | `classify_interrupt()` | Routes PATHOLOGICAL but nothing clears. Lingers forever via ior merge. |
| `tool_error` | `classify_interrupt()` | Dead code — nothing ever writes this signal. |
| `context_overflow` | `classify_interrupt()` | Dead code — nothing ever writes this signal. |
| `stabilization_action` | `route_to_next_specialist()` | Circuit breaker routing, never cleared. |

**Terminal (clearing is moot):**

| Signal | Reader | Notes |
|---|---|---|
| `user_abort` | `classify_interrupt()` | Routes to END. Workflow over. |
| `task_is_complete` | `check_task_completion()`, `after_exit_interview()` | Root-level field, `or_` reducer. EI sets True → END. |

**Write-only (ghost):**

| Signal | Writer | Problem |
|---|---|---|
| `facilitator_complete` | Facilitator | Nobody reads it. |

### The Handshake Problem

Every working signal has a **handshake** — a handler on the other side of the routing decision that acknowledges receipt and clears the flag. Every broken signal is missing that handshake. `classify_interrupt()` says "I see stagnation, go to IE/Arbiter" — but IE/Arbiter doesn't know it was invoked *because of* stagnation, so it never clears.

Adding more per-handler clearing logic is whack-a-mole. The root cause is **distributed consumption** — seven readers, five clearers (or not), three clearing mechanisms (pop, set False, set None). No single point of accountability.

### The Reducer Problem

Both `artifacts` and `scratchpad` use `Annotated[Dict[str, Any], operator.ior]`. Same type, same reducer. The `ior` merge is accumulative — once a flag is set, it persists until explicitly overwritten. "Transient" signals are aspirational, not enforced. Manual clearing (Facilitator setting `max_iterations_exceeded: False`) is the only mechanism, and it requires every handler to know about every signal it should clear.

### The Read-Only Problem

`classify_interrupt()` is a conditional edge function. In LangGraph, conditional edge functions are **read-only** — they return a routing target string but cannot write to state. This means consumption (read + clear) cannot happen at the routing decision point. It must be split: read in the edge function, clear in a subsequent node. This split is the source of the handshake gap.

## Decision

### 1. Add `signals` as a top-level GraphState field

`signals` is a sibling to `artifacts` and `scratchpad`, not a subcategory of either.

| Field | Purpose | Audience | Reducer |
|---|---|---|---|
| `artifacts` | Work products | Specialists via Facilitator | `ior` (merge) |
| `scratchpad` | Per-specialist context/observability | Facilitator, archiver | `ior` (merge) |
| `signals` | Orchestration mechanics | Signal processor node | **Replace** (snapshot) |

The replace reducer ensures each write is a complete snapshot. No stale flags. No manual clearing.

```python
def reduce_signals(old: dict, new: dict) -> dict:
    """Replace reducer — each write is a complete snapshot."""
    if new is None:
        return old    # No update from this node — keep current
    return new         # Complete replacement, stale flags gone

class GraphState(TypedDict):
    # ... existing fields ...
    signals: Annotated[Dict[str, Any], reduce_signals]
```

### 2. Introduce a signal processor node

Convert `classify_interrupt` from a conditional edge function to a **node** (`process_signals`). The node reads all signals, makes the routing decision, and returns a clean snapshot containing only the routing target and any context the destination needs. A trivial conditional edge (`route_from_signal`) reads the target string.

```python
def process_signals(state: GraphState) -> dict:
    """Read signals, decide routing, return clean snapshot."""
    signals = state.get("signals", {})

    if signals.get("user_abort"):
        target = "end"
        context = "user_abort"
        diagnostic = None
    elif signals.get("stagnation_detected"):
        target = _route_pathological("stagnation")
        context = "stagnation"
        diagnostic = {
            "stagnation_tool": signals.get("stagnation_tool"),
            "stagnation_args": signals.get("stagnation_args"),
        }
    elif signals.get("max_iterations_exceeded"):
        target = "facilitator"
        context = "benign_continuation"
        diagnostic = None
    elif signals.get("stabilization_action"):
        action = signals["stabilization_action"]
        target = action.get("target", "exit_interview")
        context = "circuit_breaker"
        diagnostic = {
            "violation_type": action.get("violation_type"),
            "last_specialist": action.get("last_specialist"),
        }
    elif signals.get("loop_detected"):
        target = "exit_interview"
        context = "loop_detected"
        diagnostic = signals["loop_detected"]  # detection details dict
    else:
        target = "router"
        context = None
        diagnostic = None

    # Replace reducer: this IS the new signal state.
    # All input signals consumed. Only routing output remains.
    result = {"routing_target": target, "routing_context": context}
    if diagnostic:
        result["diagnostic"] = diagnostic
    return {"signals": result}


def route_from_signal(state: GraphState) -> str:
    """Trivial edge function — reads what process_signals decided."""
    return state["signals"]["routing_target"]
```

### Signal snapshot shape

The output snapshot has three fields with distinct purposes:

| Field | Type | Purpose | Consumer |
|---|---|---|---|
| `routing_target` | `str` | Where to route | `route_from_signal` edge function |
| `routing_context` | `str` enum or `None` | Why we're routing there — behavioral branching | Destination specialist (e.g., Facilitator checks `"benign_continuation"`) |
| `diagnostic` | `dict` or `None` | Rich detail about the triggering condition | Archiver, EI for context, debugging |

**`routing_context` stays a simple string enum.** Current values: `"user_abort"`, `"stagnation"`, `"benign_continuation"`, `"circuit_breaker"`, `"loop_detected"`, `None`. Destinations use it for behavioral branching ("am I triaging a failure or rubber-stamping a success?").

**`diagnostic` carries structured detail.** This is where ADR-072's `completion_context` (with nested `captured_scratchpad` and `violation_type`) would live when `CompletionStatus` moves into signals. The separation prevents diagnostic richness from complicating routing decisions. Destinations optionally read diagnostic for detail; they must not need it for branching.

This avoids the cardinality problem: `routing_context` is a fixed, small enum that drives behavior. `diagnostic` is an open-ended bag of evidence that grows as the system adds detection mechanisms (drift scores, completion context, etc.) without affecting routing logic.

### 3. Migrate all routing signal writes to `signals` field

Every specialist that currently writes routing signals to `artifacts` or `scratchpad` writes to `signals` instead:

| Signal | Current writer | Current location | New location |
|---|---|---|---|
| `stagnation_detected` + `stagnation_tool` + `stagnation_args` | PD `_build_stagnation_result()` | artifacts | `signals` |
| `max_iterations_exceeded` | PD `_build_max_iterations_exceeded_result()` | artifacts | `signals` |
| `stabilization_action` | SafeExecutor (CircuitBreakerTriggered) | scratchpad | `signals` |
| `loop_detected` | `_is_unproductive_loop()` | scratchpad | `signals` |
| `forbidden_specialists` | NodeExecutor, InvariantMonitor, ImageSpecialist | scratchpad | `signals` |
| `user_abort` | External | scratchpad | `signals` |

### 4. Remove dead code

| Dead code | Location | Action |
|---|---|---|
| `tool_error` reader | `graph_orchestrator.py:513` | Delete (no writer exists) |
| `context_overflow` reader | `graph_orchestrator.py:494` | Delete (no writer exists) |
| `facilitator_complete` writer | `facilitator_specialist.py` | Delete (no reader exists) |

### 5. Remove distributed clearing logic

With the replace reducer and signal processor node, explicit clearing is no longer needed:

| Current clearing | Location | Action |
|---|---|---|
| `max_iterations_exceeded: False` | Facilitator return | Remove — replace reducer handles it |
| `loop_detected` pop | `after_exit_interview()` | Remove — replace reducer handles it |
| `forbidden_specialists: None` | SafeExecutor post-execution | Remove — replace reducer handles it |

## Consequences

### Positive

- **stagnation_detected bug fixed** — PD writes to `signals`, processor reads from `signals`. One location, one truth.
- **No stale flags** — replace reducer means every write is a clean snapshot. `ior` accumulation problem eliminated for signals.
- **Single consumption point** — all signal reading in one node. No distributed handshake problem.
- **Destination ignorance** — handlers (Facilitator, EI, Router) don't need to know about signals. They read `routing_context` for behavioral cues.
- **Dead code eliminated** — `tool_error`, `context_overflow` readers and `facilitator_complete` writer removed.
- **Cleaner artifact validation** — with routing signals separated out, `artifacts` becomes purely about work products. ADR-071's `WRITABLE_ARTIFACTS` only needs to validate work-product keys, not routing infrastructure. One less category of thing to reason about per dict. This makes ADR-076's `write_artifact` safer — a specialist writing `stagnation_detected` and `categorization_plan` to the same dict with the same `ior` reducer are structurally identical operations with completely different semantics. That conflation is eliminated.

### Negative

- **Graph topology change** — new node between specialist return and routing. Adds one hop. Minimal latency impact (no LLM call, pure Python logic).
- **Migration breadth** — touches PD, SafeExecutor, NodeExecutor, InvariantMonitor, Facilitator, graph_orchestrator, graph_builder, state.py. Wide but shallow for signal writes (move from dict X to dict Y). **Test rewrites are deeper than signal writes** — `test_interrupt_classifier.py` tests routing logic with various signal combinations. Rewriting as `test_signal_processor.py` changes the assertion shape: from `assert classify_interrupt(state) == "exit_interview"` to `assert process_signals(state)["signals"]["routing_target"] == "exit_interview"`. Every test case changes.
- **`forbidden_specialists` is both signal and context** — Router reads it for menu filtering (signal), but the information persists beyond a single routing decision (when a specialist self-excludes via ImageSpecialist pattern). This may need `forbidden_specialists` to live in scratchpad AND signals, or the self-exclusion pattern reworked. Needs investigation during implementation.

### Neutral

- **`task_is_complete` stays at root level** — it's a graph-termination flag with `or_` reducer, not a routing signal. Not migrated.
- **`recommended_specialists` stays in scratchpad** — it's a routing hint from Triage, not a signal that needs consumption semantics.

## Relationship to Future Work

- **ADR-072 (Completion Signal Protocol):** `CompletionStatus` enum could live in `signals` as a typed field alongside routing signals.
- **Typed signals (Pydantic):** Phase 2 could replace `Dict[str, Any]` with typed models (e.g., `RoutingSignal(kind, source, evidence, confidence)`). The replace reducer works identically with typed models.
- **Drift-based detection:** semantic-chunker `calculate_drift` produces a continuous score (not boolean). When implemented, stagnation would carry `confidence: 0.003` (path-seeking) vs `confidence: 0.0` (exact repetition). The `process_signals` node can then make **graduated decisions**: low confidence → continue with a warning in `routing_context`, high confidence → route to intervention. The replace reducer handles this cleanly because each signal snapshot carries the current score, not an accumulation of historical scores. If sleeptime discovers via `compare_trajectories` that a model degenerates after step N, that characterization informs the stagnation detection threshold.
- **lfm2 Reflex Arc:** 100ms models enable mid-turn signal emission at every tool call boundary. The signals field and processor node are the consumption infrastructure for this pattern.
- **Cognitive exoskeleton signals:** Future pre-flight monitors (e.g., communication pattern drift detection) write to `signals`, not scratchpad or artifacts. These are orchestration signals consumed by `process_signals` to annotate routing decisions. The replace reducer is correct behavior: you want the current measurement (re-measured from current input), not an accumulated history.
- **Pillar III (Queryable Memory):** Signals become one cell type in the multi-modal memory system. The replace reducer is the precursor to explicit lifecycle management.

## Key Files

| File | Change |
|---|---|
| `app/src/graph/state.py` | Add `signals` field with `reduce_signals` |
| `app/src/workflow/graph_orchestrator.py` | Replace `classify_interrupt` with `process_signals` node + `route_from_signal` edge |
| `app/src/workflow/graph_builder.py` | Wire `process_signals` node into graph topology |
| `app/src/specialists/project_director.py` | Move stagnation + max_iterations signals to `signals` return |
| `app/src/specialists/facilitator_specialist.py` | Read `routing_context` instead of `max_iterations_exceeded`. Remove clearing logic. Remove `facilitator_complete`. |
| `app/src/workflow/executors/node_executor.py` | Move `forbidden_specialists`, `stabilization_action` to `signals` |
| `app/src/workflow/monitors/monitor.py` | Move `forbidden_specialists` write to `signals` |
| `app/tests/unit/test_project_director.py` | Update stagnation/max_iterations assertions to `signals` |
| `app/tests/unit/test_interrupt_classifier.py` | Rewrite as `test_signal_processor.py` |
| `app/tests/unit/test_facilitator.py` | Update to test `routing_context` pattern |
