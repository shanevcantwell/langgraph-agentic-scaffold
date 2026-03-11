# ADR-CORE-064: Prompt-Prix MCP Integration

**Status:** Implemented
**Date:** 2026-02-06
**Implemented**: 2026-02-12
**Deciders:** Shane
**Context:** Cross-project integration between LAS and prompt-prix via MCP
**Relates To:** ADR-MCP-004 (LLM-Backed MCP), ADR-CORE-047 (Semantic Analysis MCP),
ADR-ROADMAP-001 (Facilitator Evolution), ADR-CORE-055 (Trace-Based ReAct Serialization)

---

## Context

LAS runs multi-model agentic workflows through a ReAct loop where models iteratively
call MCP tools (list_directory, read_file, move_file, etc.). Production observation
revealed a critical evaluation gap: **models that ace single-shot planning degrade
under accumulated context in iterative execution.**

Specific failure: gpt-oss-20b produces correct file categorization plans 10/10 times
in single-shot eval, but generates garbled tool arguments (`path='./categories?2?0??'`)
by iteration 9 of the ReAct loop.

The sibling project **prompt-prix** provides model evaluation infrastructure (LMStudio
parallel fan-out, consistency runs, LLM-as-judge). It also integrates
**semantic-chunker** for embedding-based drift measurement (`calculate_drift`).

Neither project alone could test what we needed:
- LAS has the ReAct loop, context engineering, and production traces — but no
  multi-model comparison harness
- prompt-prix has model dispatch, judging, and drift measurement — but (at the time)
  only tested single-shot exchanges

### The Tool Schema Convergence

Both projects independently evolved toward the same patterns:

| Concept | LAS | prompt-prix |
|---------|-----|-------------|
| Trace as canonical record | `ReActIteration` (ADR-CORE-055) | `ReActIteration` |
| Messages rebuilt from trace | `_serialize_for_provider()` | `build_react_messages()` |
| Cycle detection | `detect_cycle_with_pattern()` | `detect_cycle_with_pattern()` |
| Mock tool dispatch | N/A (uses live MCP) | `dispatch_mock()` with priority resolution |
| Stateless iteration | N/A (mixin owns loop) | `react_step()` MCP tool |

---

## Decision

### prompt-prix as MCP Service Provider

prompt-prix exposes its capabilities as stateless MCP tools. LAS consumes them
through the same external MCP pattern used for filesystem and semantic-chunker.

### Tool Surface

prompt-prix's MCP toolkit:

| Tool | Purpose | LAS Use Case |
|------|---------|------------|
| `react_step()` | Single ReAct iteration: trace in, new iterations out | Facilitator-driven eval loops |
| `complete()` | Base completion primitive | Direct model queries |
| `judge()` | LLM-as-judge semantic evaluation | Post-hoc response quality |
| `list_models()` | Discover available models on configured servers | Model selection |
| `calculate_drift()` | Cosine distance via semantic-chunker embeddings | Response quality degradation |

### react_step() — The Key Primitive

```python
async def react_step(
    model_id: str,
    system_prompt: str,
    initial_message: str,
    trace: list[ReActIteration],       # Previous iterations (canonical record)
    mock_tools: dict[str, dict[str, str]],  # Mock tool responses
    tools: list[dict],                 # OpenAI tool definitions
    call_counter: int = 0,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    timeout_seconds: int = 300,
) -> dict:
    # Returns:
    # {
    #     "completed": bool,           # True = model stopped calling tools
    #     "final_response": str|None,  # Text when completed
    #     "new_iterations": list[ReActIteration],
    #     "call_counter": int,         # For next call
    #     "latency_ms": float,
    # }
```

**Design principle:** Stateless. The caller owns the loop, the trace, and the
context engineering. `react_step()` dispatches one iteration to a model and returns
what happened.

### Mock Tool Dispatch (Priority Resolution)

prompt-prix resolves mock tool responses in priority order:

1. **Exact args match** — `json.dumps(args, sort_keys=True)` as lookup key
2. **First arg value match** — e.g., path value matches `read_file` call
3. **`_default` fallback** — catch-all for tool name
4. **Error** — no matching mock found

This enables deterministic eval: same mock tools → same observations → differences
are purely in the model's decisions.

---

## Two Integration Modes

### Mode 1: prompt-prix Standalone (ReactRunner)

prompt-prix's own `ReactRunner` owns the loop for its evaluation UI:

```
User uploads benchmark YAML (mode: "react")
    → ReactRunner iterates react_step() per (model × test)
    → Cycle detection at runner level
    → UI grid: ✓ complete, ⟳ cycle, ⚠ timeout
```

This mode uses prompt-prix's benchmark schema:
```json
{
    "id": "categorize_6_files",
    "mode": "react",
    "system": "...",
    "user": "Organize the files in ./sort_test into category folders.",
    "max_iterations": 15,
    "tools": [{"type": "function", "function": {"name": "read_file", ...}}],
    "mock_tools": {
        "read_file": {"./sort_test/1.txt": "The zebra is a striped animal..."},
        "create_directory": {"_default": "Directory created"},
        "move_file": {"_default": "File moved"}
    }
}
```

### Mode 2: Facilitator-Driven (LAS Orchestration)

LAS's Facilitator drives the loop, calling `react_step()` via MCP. This enables
LAS-specific context engineering that prompt-prix doesn't know about:

```
Facilitator assembles gathered_context (knowledge_base, prior traces)
    → Facilitator calls react_step(model_id, prompt, trace, mock_tools)
    → Facilitator applies error enrichment (_enrich_filesystem_error)
    → Facilitator applies context curation (ADR-ROADMAP-001 Phase 3)
    → Facilitator accumulates trace, checks stagnation
    → Loop until complete or max_iterations
```

**Why Facilitator owns this:** The ISO-9000 pattern (ADR-ROADMAP-001) designates
Facilitator as the single point of context assembly. Specialists receive context —
they don't fetch it. The same principle applies to eval: Facilitator engineers the
context that `react_step()` sees, applying the same enrichments and curation that
production uses.

This means eval tests the **full context pipeline**, not just the model's raw
capability. A model might handle clean mock responses fine but fail when Facilitator
adds `[DIR]` prefixes, error recovery hints, or prior trace history.

---

## Evaluation Axes

### Single-Shot (existing)

```yaml
# file_categorization_eval.yaml — promptfoo format
tests:
  - description: "Categorize 6 files"
    vars:
      pass_criteria: "Valid JSON with 6 correct move operations"
      expected_response: '{"operations": [...]}'  # Drift anchor
```

- `pass_criteria` → rubric for LLM judge
- `expected_response` → exemplar for `calculate_drift` (embedding cosine distance)
- These are independent evaluation axes (judge vs drift)

### ReAct Trajectory (new)

```json
{
    "mode": "react",
    "mock_tools": {...},
    "max_iterations": 15
}
```

- **Completion rate** — did the model finish all operations?
- **Cycle detection** — did it stagnate on repeated calls?
- **Arg coherence** — did tool arguments degrade over iterations?
- **Iteration count** — efficiency (fewer = better)

### Drift Threshold

`calculate_drift(actual_response, expected_response)` returns cosine distance
(0.0 = identical, 2.0 = opposite) in NV-Embed-v2 4096-dim space. Configurable
threshold — responses drifting beyond threshold are flagged as SEMANTIC_FAILURE.

---

## Trace Schema Alignment

Both projects use the same canonical trace record:

```python
class ReActIteration(BaseModel):
    iteration: int
    tool_call: ToolCall        # {id, name, args}
    observation: str           # Tool result or error
    success: bool
    thought: Optional[str]     # Model reasoning text
    latency_ms: float          # prompt-prix adds this field
```

LAS's `_serialize_for_provider()` and prompt-prix's `build_react_messages()` both
rebuild provider messages from this trace. The trace is the contract between the
two systems — as long as both serialize/deserialize `ReActIteration` consistently,
they can exchange traces.

**Archive replay**: LAS production traces (`logs/archive/*.zip` → `research_trace_N`)
can be deserialized into `ReActIteration` lists and replayed through prompt-prix to
test whether a different model would have produced a better trajectory given the
same observations.

---

## What Changed (Retroactive Record)

### In prompt-prix

1. **`react_step()` MCP tool** — stateless single-iteration ReAct primitive
2. **`ReactRunner`** — loop orchestrator with cycle detection, model-first ordering
3. **`dispatch_mock()`** — priority-based mock tool resolution
4. **`BenchmarkCase.mode = "react"`** — schema support for ReAct tests
5. **Cycle detection** — `detect_cycle_with_pattern()` (shared algorithm with LAS)
6. **`expected_response` field** — embedding anchor for drift comparison
7. **`calculate_drift()` integration** — semantic-chunker cosine distance, fail-open

### In LAS

1. **Router simplification (#140)** — `tools=[Route]` → `output_model_class=RouteResponse`,
   removing the "decoy tool" pattern. Router is a classifier, not a tool user.
2. **Drift test generator** — `scripts/generate_drift_tests.py` outputs promptfoo YAML
   with `pass_criteria` + `expected_response` per test
3. **Cross-project proposal** — `docs/proposals/PROPOSAL_Prompt-Prix-ReAct-Evaluation.md`
   documenting the integration architecture and LAS reference assets

### Not Yet Done (as of initial writing)

These items were open when the ADR was first written. See Implementation Notes below for current status.

- ~~Facilitator-driven eval loop (Mode 2)~~ — **Partially addressed**: TA consumes `react_step()` via MCP end-to-end (Phase 2c). Full Facilitator-driven mode (with context enrichment from ADR-ROADMAP-001 Phase 3) remains future work.
- Trajectory assertions beyond cycle detection (arg coherence, degradation scoring)
- Archive replay pipeline (LAS traces → prompt-prix mock sequences)

---

## Implementation Notes (Feb 2026)

### Phase 2c: TA Migration to react_step MCP (Completed)

Text Analysis Specialist migrated from local `ReActMixin` to consuming `react_step()` via prompt-prix MCP. This was the first specialist to make the transition, validating the integration pattern end-to-end.

**Validated chain**: Single NL prompt → Triage → TA → prompt-prix `react_step` → semantic-chunker `calculate_drift` x N → velocity/acceleration table → HTML report. Three containers cooperating across a single user request.

### Integration Issues Resolved

1. **CallToolResult parsing**: MCP `react_step()` returns `CallToolResult` objects, not plain dicts. Required `extract_text_from_mcp_result()` (from `mcp/utils.py`) to unwrap the text content before JSON parsing.

2. **Error visibility**: When `react_step()` hit errors inside prompt-prix (model timeout, mock dispatch miss), the error details were buried in the `CallToolResult.content` structure. Added explicit error field extraction so TA's ReAct loop could distinguish "tool failed" from "model decided to stop."

3. **Triage routing**: Triage initially didn't route semantic analysis requests to TA (it predated the MCP integration). Updated triage context to include TA's new capabilities.

### Drift Calibration Results

`calculate_drift` via semantic-chunker validated with embeddinggemma-300m (768-dim space):
- Correct file categorizations: ~0.25-0.28 drift from expected
- Semantic squelch threshold: 0.3 (above this, responses are meaningfully different)
- `judge()` deprecated in favor of `calculate_drift`/`analyze_trajectory` — embedding distance is more reproducible than LLM-as-judge

### What Remains

- **Facilitator-driven eval (Mode 2 full)**: Facilitator calling `react_step()` with its own context enrichments (error hints, path prefixes, prior trace). This is the ADR-ROADMAP-001 Phase 3 integration.
- **PD migration to react_step MCP (Phase 5)**: ProjectDirector still uses local ReActMixin. Migration planned but not yet started.
- **Archive replay pipeline**: LAS production traces → prompt-prix mock sequences for comparative model testing.
- **Trajectory assertions**: Arg coherence scoring, degradation detection beyond cycle detection.

---

## Consequences

### Positive

- **Single-shot and ReAct eval from one harness** — prompt-prix handles both modes,
  LAS doesn't need its own eval infrastructure
- **Stateless primitive enables both standalone and orchestrated use** — `react_step()`
  serves prompt-prix's ReactRunner AND future Facilitator-driven loops
- **Mock tools make ReAct eval deterministic** — same mocks → same observations →
  differences are in model capability, not environment
- **Trace portability** — shared `ReActIteration` schema means traces flow between
  projects without translation

### Negative

- **Two loop owners** — ReactRunner (prompt-prix) and future Facilitator (LAS) both
  manage ReAct loops. Must ensure they accumulate trace the same way.
- **Context engineering gap** — prompt-prix's ReactRunner uses clean mock responses.
  LAS's Facilitator adds enrichments (path prefixes, error hints). Models tested in
  prompt-prix may behave differently in LAS production. Mode 2 addresses this but
  isn't implemented yet.
- **Schema coupling** — `ReActIteration` is now a cross-project contract. Changes
  in either project must be coordinated.
