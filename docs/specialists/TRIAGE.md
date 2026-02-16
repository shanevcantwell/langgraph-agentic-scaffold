# Triage Architect Briefing: Intent Classification and Context Planning in LAS

**Purpose:** Technical briefing on the TriageArchitect specialist's role as the entry gate.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-16 (#199: Triage→SA pipeline flip, ACCEPT/REJECT classifier rewrite)

---

## Executive Summary

The **TriageArchitect** is the **entry point** — the first node in the pipeline. It answers one question: **should the system invest in this request?** Triage is a pure ACCEPT/REJECT gate. Rejection via `ask_user` fires before SA invests an LLM call on planning.

Key characteristics:
- **First in entry pipeline** — Triage → SA → Facilitator → Router → Specialist (#199)
- **LLM-based ACCEPT/REJECT classifier** — makes one LLM call with structured output to produce a `ContextPlan`
- **Gate before investment** — rejection fires before SA planning, not after (#199)
- **Does not execute** — Triage classifies; it never gathers context or does work itself
- **No specialist routing** — Triage does not recommend specialists. That responsibility belongs to SA (via `task_plan`) and Router (via LLM reasoning)

---

## Where Triage Fits in the Execution Flow

### Every Request

```
User submits request
    |
state_factory.py: artifacts["user_request"] = goal  (line 70)
    |
    v
TriageArchitect (LLM: ACCEPT/REJECT gate, #199)
    |
    +-- scratchpad["triage_reasoning"] = reasoning string
    +-- scratchpad["triage_actions"]   = [{type, target, description}, ...]
    |
    v
check_triage_outcome()  [graph_orchestrator.py]
    |
    +-- PASS (no actions, or non-ask_user actions) --> SystemsArchitect --> Facilitator --> Router --> Specialist
    +-- CLARIFY (ask_user only) --> end_specialist (reject with cause, #179)
```

### Triage Does NOT Run on Retry

When EI says INCOMPLETE, the retry path goes directly to Facilitator:

```
EI says INCOMPLETE
    |
    v
Facilitator (rebuild gathered_context with trace knowledge)
    |
    v
Router (LLM selects specialist based on task_plan + gathered_context)
    |
    v
Specialist (PD, etc.)
```

Triage runs exactly **once per user request**. Its scratchpad entries persist across retries — Facilitator re-reads `triage_actions` each time to get the plan actions.

---

## What Triage Produces

### ContextPlan Schema (Wire Format)

```python
# From context_schema.py
class ContextPlan(BaseModel):
    """Triage's forced-tool-call wire format. Not persisted as an artifact --
    actions flow to scratchpad['triage_actions'], reasoning to scratchpad['triage_reasoning'].
    """
    actions: List[ContextAction] = []         # What context to gather
    reasoning: str                            # Why these actions are needed

class ContextAction(BaseModel):
    type: ContextActionType   # RESEARCH | READ_FILE | SUMMARIZE | LIST_DIRECTORY | ASK_USER
    target: str               # Query, file path, or text
    description: str          # Why this action is needed
    strategy: Optional[str]   # Provider hint (e.g., "google", "duckduckgo")
```

`ContextPlan` is a **wire format** for Triage's structured output — the LLM must produce this structure via `output_model_class` (logit-masked schema enforcement). The plan is NOT stored as an artifact. Instead, its fields are decomposed to scratchpad.

### Output: Scratchpad Only

```python
# triage_architect.py:88-94
return {
    "scratchpad": {
        "triage_reasoning": context_plan.reasoning,
        "triage_actions": [a.model_dump() for a in context_plan.actions],
    }
}
```

| Key | Location | Consumer | Purpose |
|-----|----------|----------|---------|
| `triage_actions` | scratchpad | Facilitator | Execute context-gathering actions |
| `triage_actions` | scratchpad | check_triage_outcome() | Route: actions → Facilitator, ask_user-only → END, empty → Router |
| `triage_actions` | scratchpad | EndSpecialist | Format ask_user questions as rejection message (#179) |
| `triage_reasoning` | scratchpad | Observability | Logging, archive forensics |

---

## Prompt Assembly: What the Model Sees

### Loading Chain

```
config.yaml
  specialists.triage_architect.prompt_file: "triage_architect_prompt.md"
  specialists.triage_architect.llm_config: "lmstudio"
    |
    v
GraphBuilder._configure_triage()          [graph_builder.py]
    |
    +-- load_prompt("triage_architect_prompt.md")
          Static base: action types, examples, ask_user guidance
```

Unlike other specialists, Triage's prompt assembly historically included a dynamic specialist roster. This was removed because:
1. SA's `task_plan` already captures intent — Router doesn't need Triage's specialist advice
2. The roster injection caused MoE models to garble output (prompt was ~50% longer than needed)

### What the LLM Receives

**System prompt** = base prompt from `triage_architect_prompt.md` (no dynamic injection)

**Messages** = enriched via `_get_enriched_messages(state)`:
- The user's message from `messages[-1]`
- Optionally: system notes appended for uploaded content (Blind Triage Support)

**Output schema** = `ContextPlan` as structured output:
```python
request = StandardizedLLMRequest(
    messages=messages,
    output_model_class=ContextPlan,   # Direct schema enforcement via logit masking
)
```

`output_model_class` enforces ContextPlan's flat schema directly. NOT `tools=[ContextPlan]` — that wraps ContextPlan in a nested tool-call envelope with duplicate fields, confusing models into producing `"..."` (#199).

---

## Routing Decision: check_triage_outcome()

`check_triage_outcome()` in [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) implements a **two-way gate** (#199):

```python
def check_triage_outcome(self, state: GraphState) -> str:
    triage_actions = state.get("scratchpad", {}).get("triage_actions", [])

    if triage_actions:
        ask_user_count = sum(1 for a in triage_actions if a.get("type") == "ask_user")
        other_count = len(triage_actions) - ask_user_count

        # #179: Ask-user-only = underspecified prompt. Reject with cause.
        if other_count == 0 and ask_user_count > 0:
            return CoreSpecialist.END.value   # CLARIFY -> reject

        # Non-ask_user actions = PASS (legacy action types from before classifier rewrite)
        return "systems_architect"

    return "systems_architect"                # PASS -> SA for planning
```

This means:
- **PASS** (no actions, or non-ask_user actions) -> SystemsArchitect -> Facilitator -> Router -> Specialist
- **CLARIFY** (ask_user only) -> EndSpecialist formats rejection (#179)

The decision is purely structural (are there ask_user-only actions?) not semantic (what kind of task?). Specialist selection is Router's job. The old three-way gate (Facilitator vs Router vs END) was collapsed into two paths because Facilitator always runs via the SA -> Facilitator unconditional edge (#199).

---

## How Triage's Output Flows Downstream

### Path 1: Facilitator Reads triage_actions

Facilitator always runs (unconditional SA -> Facilitator edge). It reads `scratchpad["triage_actions"]` and:

1. Parses each action dict into a `ContextAction` for type-safe dispatch
2. Iterates through actions, calling MCP services for each (RESEARCH -> web search, READ_FILE -> filesystem, etc.)
3. Assembles results into `gathered_context` artifact
4. Task Strategy comes from `task_plan.plan_summary` + `acceptance_criteria` (SA's intent capture), not from Triage reasoning
5. If triage_actions is empty, context assembly still runs — builds Task Strategy, prior work, and EI feedback without plan action results

See [FACILITATOR.md](./FACILITATOR.md) for the full context assembly story.

### Path 2: triage_actions Persists Across Retries

On retry (EI said INCOMPLETE), Facilitator re-reads `scratchpad["triage_actions"]` to:
- Re-execute plan actions (e.g., re-list directory to see current state)
- Add EI feedback and accumulated prior work alongside the action results

The scratchpad entries are **immutable after Triage writes them**. No downstream specialist modifies them.

---

## Data Injection: Blind Triage Support

Triage handles uploaded content by appending system notes to the user's message:

### Uploaded Text

```python
# triage_architect.py:32-38
if state.get("artifacts", {}).get("text_to_process"):
    messages[-1] = HumanMessage(content=last_content +
        f"\n\n[SYSTEM NOTE: The user has uploaded a document ({text_length} characters). "
        "This document is ALREADY AVAILABLE in artifacts - you do NOT need to gather it. "
        "Do NOT emit READ_FILE or RESEARCH actions to obtain this document. "
        "Emit an empty actions list and recommend an appropriate specialist to process it.]")
```

### Uploaded Image

```python
# triage_architect.py:41-47
if state.get("artifacts", {}).get("uploaded_image.png"):
    messages[-1] = HumanMessage(content=last_content +
        "\n\n[SYSTEM NOTE: The user has uploaded an image. "
        "You cannot see it, but it is available in the artifacts. Do not ask for the image.]")
```

These notes prevent Triage from emitting redundant READ_FILE actions for content that's already in artifacts.

---

## Error Handling and Fallbacks

### No Valid JSON Returned

If the LLM returns empty or invalid JSON (shouldn't happen with `output_model_class` logit masking, but models misbehave):

```python
if not plan_args:
    return self._fallback_plan("LLM did not return valid JSON")
```

### Malformed Fields (#154)

Guard against models returning non-list `actions` or empty `reasoning`:

```python
if not isinstance(plan_args.get("actions"), list):
    plan_args["actions"] = []
if not plan_args.get("reasoning"):
    plan_args["reasoning"] = "Context plan generated (reasoning was empty)"
```

### Pydantic Validation Failure

If `ContextPlan(**plan_args)` raises `ValidationError`, Triage salvages what it can:

```python
except ValidationError as ve:
    context_plan = ContextPlan(
        reasoning=plan_args.get("reasoning", "Validation fallback"),
    )
```

### Fallback Plan

All error paths produce a valid scratchpad with empty actions:

```python
def _fallback_plan(self, reason: str) -> Dict[str, Any]:
    fallback = ContextPlan(reasoning=f"Triage fallback: {reason}")
    return {
        "messages": [AIMessage(content=f"[Triage] {reason}")],
        "scratchpad": {
            "triage_reasoning": fallback.reasoning,
            "triage_actions": [],
        }
    }
```

Empty actions means `check_triage_outcome()` routes to SystemsArchitect (PASS). The system never stalls on a Triage failure — it falls through to SA with degraded (but functional) state.

---

## What Triage Does NOT Do

| Capability | Triage | Who Does It |
|------------|--------|-------------|
| Execute context actions | No | Facilitator |
| Route to specialists | No | Router (LLM reasoning over task_plan + gathered_context) |
| Recommend specialists | No | SA (task_plan); Router (LLM selection) |
| Create execution plans | No | SA (entry point: task_plan; MCP: project_plan, exit_plan) |
| Accumulate context | No | Facilitator (sole context writer) |
| Run on retry | No | Runs once; scratchpad persists for Facilitator |
| Write user_request | No | state_factory.py writes it at initialization |

---

## Triage Ticket vs. Task Plan (#171, #199)

Triage produces a **ticket**, not a plan. In real-world triage (medical, IT, support), triage outputs a classification and routing decision — the specialist makes the plan.

| Output | What It Is | Schema | Producer |
|--------|-----------|--------|----------|
| `triage_actions` / `triage_reasoning` | Triage ticket: ACCEPT/REJECT classification | ContextPlan (wire format) | Triage (LLM call, runs first) |
| `task_plan` | System's theory of user intent | SystemPlan | SA (runs second, after Triage PASS) |

Triage runs first as the ACCEPT/REJECT gate (#199). On PASS, SA runs second and produces `task_plan`. Triage classifies prompt completeness — it doesn't plan the task or select specialists.

### Plan Hierarchy

The `task_plan` is the master plan. Specialist-specific plans derive from it:

```
Triage (entry gate) -> triage_actions / triage_reasoning (scratchpad)
    |
SA (planning) -> task_plan (artifacts, includes acceptance_criteria #173)
    |
    +-- PD calls SA MCP -> project_plan (PD-specific steps)
    +-- EI calls SA MCP -> exit_plan (verification of task_plan)
    +-- WebBuilder calls SA MCP -> system_plan (web implementation, #172)
```

All plans are write-once, read-many. The `task_plan` persists across retries.

See [SYSTEMS_ARCHITECT.md](./SYSTEMS_ARCHITECT.md) for the plan-first architecture and SA's dual role (planning node + MCP service).

---

## Graph Classification

Triage is the **first node** in the entry pipeline, wired by `ContextEngineeringSubgraph` ([context_engineering.py](../../app/src/workflow/subgraphs/context_engineering.py)):

```
Triage (entry gate) -> [SA | END]
SA -> Facilitator -> Router
```

- Triage is the graph entry point (`config.yaml: entry_point: "triage_architect"` in the subgraph wiring, though config still lists SA as the named entry_point for backward compat)
- Triage -> SA/END is a conditional edge via `check_triage_outcome()` (two-way: PASS or CLARIFY)
- SA -> Facilitator is an unconditional edge (SA always hands off to Facilitator)
- Facilitator -> Router is an unconditional edge
- Triage is excluded from Router's specialist menu (TRIAGE_INFRASTRUCTURE)
- Triage is excluded from hub-and-spoke edges (subgraph-managed via `get_excluded_specialists()`)

---

## Configuration

### Specialist Registration (config.yaml)

```yaml
workflow:
  entry_point: "systems_architect"   # Named entry point (SA), but Triage is wired first via subgraph

specialists:
  triage_architect:
    type: "llm"
    prompt_file: "triage_architect_prompt.md"
    description: "ACCEPT/REJECT gate — classifies prompt completeness before SA investment"
    tags: ["planning", "context_engineering"]
```

The `tags` are significant: they identify Triage as a planning specialist for graph wiring purposes. Note: `entry_point` in config names SA, but `ContextEngineeringSubgraph` wires Triage as the actual first node via conditional edges (#199).

---

## Archive Forensics

### Verify Triage Ran

```bash
# Check routing history -- triage_architect should be [0] (entry gate, #199)
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history[0:3]'
```

### Check What Triage Produced

```bash
# See reasoning and actions from scratchpad
unzip -p ./logs/archive/run_*.zip final_state.json | \
  jq '{reasoning: .scratchpad.triage_reasoning, actions: .scratchpad.triage_actions}'
```

### Check Triage LLM Trace

```bash
# Triage's LLM call is in llm_traces.jsonl
unzip -p ./logs/archive/run_*.zip llm_traces.jsonl | grep triage_architect | jq .
```

---

## Key Files

| File | Purpose |
|------|---------|
| [triage_architect.py](../../app/src/specialists/triage_architect.py) | TriageArchitect implementation |
| [triage_architect_prompt.md](../../app/prompts/triage_architect_prompt.md) | System prompt (action types, examples) |
| [context_schema.py](../../app/src/interface/context_schema.py) | `ContextPlan`, `ContextAction`, `ContextActionType` schemas (wire format) |
| [graph_builder.py](../../app/src/workflow/graph_builder.py) | `_configure_triage()` prompt loading |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_triage_outcome()` three-way routing gate |
| [state_factory.py](../../app/src/graph/state_factory.py) | `user_request` artifact initialization (line 70) |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Primary consumer of `triage_actions` |
| [end_specialist.py](../../app/src/specialists/end_specialist.py) | Consumer of ask_user actions for rejection (#179) |
| [test_triage_architect.py](../../app/tests/unit/test_triage_architect.py) | Unit tests (plan generation, fallbacks, blind triage) |
| [test_triage_routing_flow.py](../../app/tests/integration/test_triage_routing_flow.py) | Integration test (end-to-end routing validation) |

---

## Summary

The TriageArchitect is the **ACCEPT/REJECT entry gate** that:

1. Receives the raw user request (first node in pipeline, #199)
2. Makes one LLM call with structured output (`output_model_class=ContextPlan`) to classify prompt completeness
3. Writes actions and reasoning to scratchpad (no artifact)
4. Routes to SA (PASS — any non-ask_user result) or END (CLARIFY — ask_user only, #179)
5. Runs exactly once per request — scratchpad entries persist across retries for Facilitator to re-read

Triage answers **"should the system invest in this request?"** It does not answer **"who should do the work?"** (Router) or **"how should the work be done?"** (SA via `task_plan`).
