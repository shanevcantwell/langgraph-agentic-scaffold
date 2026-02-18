# Signal Processor Briefing: Procedural Interrupt Classification in LAS

**Purpose:** Technical briefing on the Signal Processor specialist's role as the routing decision layer.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-18 (ADR-077: Signal Processor Architecture, #200)

---

## Executive Summary

The **Signal Processor** is a procedural specialist (no LLM) that sits between every non-terminal specialist and the routing decision layer. It reads routing signals from the `signals` GraphState field and `scratchpad`, then produces a routing decision as a clean signals snapshot consumed by the `route_from_signal` edge function.

Key characteristics:
- **Procedural, not LLM-based** — deterministic priority chain, no inference calls
- **SafeExecutor-wrapped** — gets routing_history tracking, state_timeline entries, and error handling for free
- **Single accountability point** — all interrupt classification in one place (replaces the bare `classify_interrupt()` function that was scattered across GraphOrchestrator)
- **Replace reducer** — the `signals` field uses a replace reducer (not ior merge), so each write is a complete snapshot. Stale flags cannot linger.
- **CORE_INFRASTRUCTURE** — excluded from Router menu, Triage menu, and hub-and-spoke edges automatically

---

## Where Signal Processor Fits in the Execution Flow

### Graph Topology (ADR-077)

```
Specialist (e.g., PD, WebBuilder, TA)
    |
    [unconditional edge]
    |
SignalProcessorSpecialist
    |
    [route_from_signal — conditional edge]
    |
    |--> exit_interview_specialist    (artifacts present, or BENIGN, or circuit breaker)
    |--> router_specialist            (no artifacts, no signals — continue workflow)
    |--> end_specialist               (user_abort)
    |--> facilitator_specialist       (retry routing)
    '--> interrupt_evaluator_specialist (stagnation — if available)
```

**Terminal specialists** (chat, default_responder, tiered_synthesizer) bypass the signal processor entirely — they route through `check_task_completion` directly.

### Before vs After ADR-077

| Before | After |
|--------|-------|
| `specialist → classify_interrupt (conditional edge) → {EI, Router, END, ...}` | `specialist → unconditional edge → signal_processor (node) → route_from_signal (edge) → {EI, Router, END, ...}` |
| Signal reads scattered: artifacts, scratchpad, both | Signal reads centralized: `signals` field + `scratchpad` (externally set only) |
| No observability on routing decisions | SafeExecutor gives routing_history, state_timeline entries |
| Ghost signals (`facilitator_complete`, `tool_error`, `context_overflow`) | Dead code removed |

---

## The `signals` GraphState Field

```python
# state.py
def reduce_signals(current: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """Replace reducer — each write is a complete snapshot, not a merge."""
    if update is None:
        return current
    return update

signals: Annotated[Dict[str, Any], reduce_signals]
```

**Why replace, not ior?** With `operator.ior` (used by artifacts/scratchpad), a flag like `stagnation_detected: True` would persist across specialist invocations because merge never removes keys. Replace semantics mean each specialist writes a complete snapshot — if a signal isn't in the snapshot, it's gone.

### Signal Writers

| Signal | Writer | When |
|--------|--------|------|
| `stagnation_detected` + `stagnation_tool` + `stagnation_args` | PD (`_build_stagnation_result`) | Cycle detected in react trace |
| `max_iterations_exceeded` | PD (`_build_partial_result`) | Hit max_iterations budget |
| `stabilization_action` | SafeExecutor CB handler | Circuit breaker triggered |

### Signals That Stay in Scratchpad

| Signal | Reason |
|--------|--------|
| `user_abort` | Externally set by client/UI — not a specialist output |
| `loop_detected` | Set by edge functions via direct state mutation — different graph path |
| `forbidden_specialists` | Router menu constraint — not a routing signal |

---

## Priority Chain

Signal Processor evaluates signals in strict priority order. First match wins:

| Priority | Condition | Target | routing_context | Classification |
|----------|-----------|--------|-----------------|----------------|
| 1 | `signals.stabilization_action == "ROUTE_TO_ERROR_HANDLER"` | EI (or END if no EI) | `"circuit_breaker"` | Circuit breaker |
| 2 | `scratchpad.user_abort` | END | `"user_abort"` | Terminal |
| 3 | `signals.max_iterations_exceeded` | EI | `"benign_continuation"` | BENIGN |
| 4 | `signals.stagnation_detected` | IE → EI → Router (fallback chain) | `"stagnation"` | PATHOLOGICAL |
| 5 | `artifacts` is non-empty | EI | `None` | Normal completion |
| 6 | No artifacts, no signals | Router | `None` | Normal continuation |

---

## Signal Output Schema

Signal Processor writes **only** to the `signals` field. Each invocation produces a complete snapshot:

```python
{
    "signals": {
        "routing_target": "exit_interview_specialist",   # consumed by route_from_signal
        "routing_context": "benign_continuation",        # consumed by Facilitator, archiver
        "diagnostic": {                                  # optional, for stagnation
            "stagnation_tool": "read_file",
            "stagnation_args": {"path": "/workspace/test/1.txt"}
        }
    }
}
```

| Field | Type | Consumer |
|-------|------|----------|
| `routing_target` | `str` | `route_from_signal` edge function — determines next graph node |
| `routing_context` | `str \| None` | Facilitator reads `"benign_continuation"` for BENIGN early return. Archiver/debugging. |
| `diagnostic` | `dict \| None` | Stagnation details: tool name + args. Observability only. |

---

## Fallback Chains

### Circuit Breaker Stabilization

```python
def _resolve_stabilization_target(self) -> str:
    if "exit_interview_specialist" in self._specialist_names:
        return "exit_interview_specialist"
    return "end_specialist"
```

EI can evaluate recoverability. If EI isn't loaded, route to END (safe halt).

### Pathological (Stagnation)

```python
def _route_pathological(self) -> str:
    if "interrupt_evaluator_specialist" in self._specialist_names:
        return "interrupt_evaluator_specialist"
    if "exit_interview_specialist" in self._specialist_names:
        return "exit_interview_specialist"
    return "router_specialist"
```

Fallback chain: Interrupt Evaluator → Exit Interview → Router. Each fallback is checked against the actual specialist map injected at graph build time.

---

## Downstream Consumers

### Facilitator: BENIGN Detection

Facilitator reads `routing_context` from the signals field to detect BENIGN continuation:

```python
routing_context = state.get("signals", {}).get("routing_context")
is_benign_continuation = routing_context == "benign_continuation"
```

**Signal persistence proof:** Signal Processor writes `routing_context: "benign_continuation"` → EI runs (uses `after_exit_interview` edge, not signal processor path, so signals aren't overwritten) → Facilitator reads `routing_context` still set. Correct.

### route_from_signal Edge Function

Trivial conditional edge on GraphOrchestrator:

```python
def route_from_signal(self, state: GraphState) -> str:
    signals = state.get("signals", {})
    target = signals.get("routing_target")
    if not target:
        logger.warning("No routing_target in signals, falling back to Router")
        return CoreSpecialist.ROUTER.value
    return target
```

---

## Configuration

```yaml
# config.yaml
signal_processor_specialist:
  type: "procedural"
  description: "Procedural interrupt classifier. Reads routing signals, determines next graph destination."
  excluded_from:
    - triage_architect
    - router_specialist
```

- `type: "procedural"` — no `llm_config` required, `_attach_llm_adapter` checks for `config.get("llm_config")` and skips.
- `CORE_INFRASTRUCTURE` + `TRIAGE_INFRASTRUCTURE` in specialist_categories.py — automatically excluded from Router menu, Triage menu, and hub-and-spoke edges.

---

## Graph Builder Wiring

```python
# graph_builder.py — _wire_hub_and_spoke_edges
signal_processor_name = CoreSpecialist.SIGNAL_PROCESSOR.value
has_signal_processor = signal_processor_name in self.specialists

for name in self.specialists:
    if name in excluded_specialists:
        continue
    if name in terminal_specialists:
        workflow.add_conditional_edges(name, self.orchestrator.check_task_completion, ...)
    elif has_signal_processor:
        workflow.add_edge(name, signal_processor_name)  # unconditional
    else:
        workflow.add_conditional_edges(name, self.orchestrator.check_task_completion, ...)

if has_signal_processor:
    workflow.add_conditional_edges(signal_processor_name,
                                   self.orchestrator.route_from_signal,
                                   signal_processor_destinations)
```

**Graceful degradation:** When signal processor is absent (minimal test configs), all specialists fall back to `check_task_completion`. This prevents test fixtures from needing to include every infrastructure specialist.

**`add_conditional_edges` is additive** (lesson from #160) — the signal processor gets exactly ONE `add_conditional_edges` call. The loop adds only unconditional edges to it.

---

## What Signal Processor Does NOT Do

- **No LLM calls** — purely procedural, deterministic
- **No artifact writes** — returns only `{"signals": snapshot}`
- **No scratchpad writes** — routing decisions visible through signals + state_timeline
- **No loop detection** — `loop_detected` is set by edge functions via direct state mutation. Different graph path.
- **No `user_abort` migration** — externally set by client, stays in scratchpad
- **No `forbidden_specialists` handling** — Router menu constraint, not a routing signal

---

## Archive Forensics

```bash
# Check signal processor routing decisions in state_timeline
unzip -p ./logs/archive/run_*.zip state_timeline.jsonl | grep signal_processor | jq .

# Check routing_history for signal processor appearances
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check signals in final state
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.signals'
```

**Key things to check:**
- Signal processor appears in `routing_history` between executing specialist and its target
- `signals.routing_target` matches the actual next specialist in `routing_history`
- `signals.routing_context` is `"benign_continuation"` when PD hit max_iterations
- `signals.diagnostic` contains stagnation details when stagnation was detected

---

## Key Files

| File | Purpose |
|------|---------|
| [signal_processor_specialist.py](../../app/src/specialists/signal_processor_specialist.py) | Priority chain, fallback routing, signal snapshot builder |
| [state.py](../../app/src/graph/state.py) | `reduce_signals` function, `signals` field in GraphState |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `route_from_signal()` edge function, `_check_stabilization_action()` defense-in-depth |
| [graph_builder.py](../../app/src/workflow/graph_builder.py) | Unconditional edges to signal processor, conditional edge from it |
| [specialist_categories.py](../../app/src/workflow/specialist_categories.py) | `CORE_INFRASTRUCTURE` + `TRIAGE_INFRASTRUCTURE` membership |
| [project_director.py](../../app/src/specialists/project_director.py) | Writes `stagnation_detected`, `max_iterations_exceeded` to `signals` |
| [node_executor.py](../../app/src/workflow/executors/node_executor.py) | Writes `stabilization_action` to `signals` (circuit breaker) |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Reads `routing_context` from `signals` for BENIGN detection |

---

## Summary

The Signal Processor is a **procedural routing classifier** that:

1. Reads specialist-produced signals from the `signals` GraphState field (replace reducer)
2. Evaluates a strict 6-level priority chain (circuit breaker > user abort > BENIGN > stagnation > normal completion > continuation)
3. Produces a routing decision as a clean signals snapshot (`routing_target`, `routing_context`, `diagnostic`)
4. Gets consumed by the trivial `route_from_signal` edge function
5. Provides observability for free via SafeExecutor wrapping (routing_history, state_timeline)

It replaces the monolithic `classify_interrupt()` function that read signals from multiple scattered locations (artifacts, scratchpad) with inconsistent semantics.
