# Triage Architect Briefing: Intent Classification and Context Planning in LAS

**Purpose:** Technical briefing on the TriageArchitect specialist's role as the classifier and routing advisor.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-12 (#171 SA as entry point)

---

## Executive Summary

The **TriageArchitect** produces a **triage ticket** — classification, routing recommendation, and intake prep actions. It answers two questions: **what context is needed** (actions for Facilitator) and **who should do the work** (recommendations for Router).

Triage is NOT the entry point. SA runs first to produce a `task_plan` (the system's theory of user intent), then Triage classifies with the benefit of that plan.

Key characteristics:
- **Second in entry pipeline** — SA → Triage → [Facilitator] → Router → Specialist (#171)
- **LLM-based classifier** — makes one LLM call with forced tool use to produce a structured `ContextPlan` (triage ticket)
- **Dynamic specialist menu** — system prompt is enriched at startup with the current specialist roster (names + descriptions)
- **Does not execute** — Triage classifies and recommends; it never gathers context or does work itself

---

## Where Triage Fits in the Execution Flow

### Every Request

```
User submits request
    |
state_factory.py: artifacts["user_request"] = goal  (line 70)
    |
    ▼
SystemsArchitect (entry point, #171)
    writes artifacts["task_plan"]  — system's theory of user intent
    |
    ▼
TriageArchitect (LLM: classifies intent, creates triage ticket)
    |
    ├─ artifacts["context_plan"]  = {actions, reasoning, recommended_specialists}
    └─ scratchpad = {triage_reasoning, recommended_specialists}
    |
    ▼
check_triage_outcome()  [graph_orchestrator.py:34-68]
    |
    ├── actions present?  → facilitator_specialist  → Router → Specialist
    └── no actions?       → router_specialist (direct)
```

### Triage Does NOT Run on Retry

When EI says INCOMPLETE, the retry path goes directly to Facilitator:

```
EI says INCOMPLETE
    |
    ▼
Facilitator (rebuild gathered_context with trace knowledge)
    |
    ▼
Router (reuses scratchpad["recommended_specialists"] from original Triage)
    |
    ▼
Specialist (PD, etc.)
```

Triage runs exactly **once per user request**. Its `context_plan` artifact persists across retries — Facilitator re-reads it each time to get the plan actions and reasoning.

---

## What Triage Produces

### ContextPlan Schema

```python
# From context_schema.py
class ContextPlan(BaseModel):
    actions: List[ContextAction] = []         # What context to gather
    reasoning: str                            # Why (becomes "Task Strategy" in gathered_context)
    recommended_specialists: List[str] = []   # Who should do the work

class ContextAction(BaseModel):
    type: ContextActionType   # RESEARCH | READ_FILE | SUMMARIZE | LIST_DIRECTORY | ASK_USER
    target: str               # Query, file path, or text
    description: str          # Why this action is needed
    strategy: Optional[str]   # Provider hint (e.g., "google", "duckduckgo")
```

### Output Artifact and Scratchpad

```python
# triage_architect.py:89-97
return {
    "artifacts": {
        "context_plan": context_plan.model_dump()
    },
    "scratchpad": {
        "triage_reasoning": context_plan.reasoning,
        "recommended_specialists": context_plan.recommended_specialists
    }
}
```

Both `artifacts` and `scratchpad` carry the same information, but serve different consumers:

| Key | Location | Consumer | Purpose |
|-----|----------|----------|---------|
| `context_plan` | artifacts | Facilitator | Execute actions, surface reasoning as "Task Strategy" |
| `context_plan` | artifacts | Facilitator (on retry) | Re-read reasoning and actions for fresh context rebuild |
| `triage_reasoning` | scratchpad | Observability | Logging, archive forensics |
| `recommended_specialists` | scratchpad | Router | Advisory routing hint (consumed then cleared) |

---

## Prompt Assembly: What the Model Sees

### Loading Chain

```
config.yaml
  specialists.triage_architect.prompt_file: "triage_architect_prompt.md"
  specialists.triage_architect.llm_config: "lmstudio"
    │
    ▼
GraphBuilder._configure_triage()          [graph_builder.py:429-484]
    │
    ├── load_prompt("triage_architect_prompt.md")
    │     Static base: action types, routing heuristics, examples
    │
    ├── SpecialistCategories.get_triage_exclusions()
    │     Removes: MCP_ONLY, INTERNAL_ONLY, subgraph-managed, config-excluded, self
    │
    ├── Filter to type="llm" only
    │     Removes: procedural specialists (Facilitator, NodeExecutor)
    │
    └── Append dynamic roster:
          "--- AVAILABLE SPECIALISTS ---
           You MUST choose one or more of the following specialists:
           - chat_specialist: Handles simple Q&A...
           - project_director: Autonomous agent for multi-step tasks...
           - web_builder: Builds and modifies web UIs...
           - text_analysis_specialist: Semantic drift, data extraction..."
```

### What the LLM Receives

**System prompt** = base prompt + specialist roster (assembled once at startup, identical for all requests)

**Messages** = enriched via `_get_enriched_messages(state)`:
- The user's message from `messages[-1]`
- Optionally: system notes appended for uploaded content (Blind Triage Support)

**Tool schema** = `ContextPlan` as a forced tool call:
```python
request = StandardizedLLMRequest(
    messages=messages,
    tools=[ContextPlan],
    force_tool_call=True   # LLM MUST produce a ContextPlan, no free-text
)
```

`force_tool_call=True` means the LLM has no option to respond without producing a ContextPlan. The tool schema defines `actions`, `reasoning`, and `recommended_specialists` fields via Pydantic → OpenAI function calling format.

---

## Routing Decision: actions vs. no actions

`check_triage_outcome()` in [graph_orchestrator.py:34-68](../../app/src/workflow/graph_orchestrator.py#L34-L68) implements a binary gate:

```
context_plan.actions is non-empty?
    ├── YES → facilitator_specialist
    └── NO  → router_specialist
```

This means:
- **Simple greeting** ("hello") → empty actions, Triage recommends `default_responder_specialist` → straight to Router
- **File task** ("sort these files") → `LIST_DIRECTORY` action → Facilitator gathers context first → then Router
- **Research task** ("find current GPU prices") → `RESEARCH` action → Facilitator does web search → then Router
- **Semantic analysis** ("calculate drift between these prompts") → empty actions, recommends `text_analysis_specialist` → straight to Router

The decision is purely structural (are there actions?) not semantic (what kind of task?). Specialist selection is Router's job, not Triage's.

---

## How Triage's Output Flows Downstream

### Path 1: Facilitator Reads context_plan

Facilitator reads `artifacts["context_plan"]` ([facilitator_specialist.py:263-272](../../app/src/specialists/facilitator_specialist.py#L263-L272)) and:

1. Surfaces `context_plan.reasoning` as `### Task Strategy` in gathered_context ([line 277-279](../../app/src/specialists/facilitator_specialist.py#L277-L279))
2. Iterates through `context_plan.actions`, calling MCP services for each (RESEARCH → web_specialist, READ_FILE → filesystem, etc.)
3. Assembles results into `gathered_context` artifact

See [FACILITATOR.md](./FACILITATOR.md) for the full context assembly story.

### Path 2: Router Reads recommended_specialists

Router reads `scratchpad["recommended_specialists"]` ([router_specialist.py:203](../../app/src/specialists/router_specialist.py#L203)) and classifies the recommendation:

| Source | Treatment | Mechanism |
|--------|-----------|-----------|
| Triage recommendation | **Advisory** — injected into Router's prompt as suggestion, LLM may override | `"TRIAGE SUGGESTIONS (ADVISORY, NOT MANDATORY)"` |
| Specialist dependency | **Deterministic** — if single target, bypass LLM entirely | `routing_type: "deterministic_dependency"` |

Router distinguishes these by checking `routing_history`: if the last non-planning specialist in the history made the recommendation, it's a dependency. If it came from Triage/Facilitator (tagged `"planning"` or `"context_engineering"`), it's advisory.

After using the recommendation, Router **clears it**: `scratchpad["recommended_specialists"] = None` ([line 441](../../app/src/specialists/router_specialist.py#L441)). This prevents stale recommendations from influencing future routing cycles.

### Path 3: context_plan Persists Across Retries

On retry (EI said INCOMPLETE), Facilitator re-reads `artifacts["context_plan"]` to:
- Re-surface `reasoning` as Task Strategy (fresh rebuild, not accumulated)
- Re-execute plan actions if any (e.g., re-list directory to see current state)
- Add EI feedback and trace knowledge alongside the original Triage reasoning

The `context_plan` artifact is **immutable after Triage writes it**. No downstream specialist modifies it.

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

### No Tool Call Returned (#154)

If the LLM responds without a tool call (shouldn't happen with `force_tool_call=True`, but models misbehave):

```python
if not tool_calls:
    return self._fallback_plan("LLM did not return a tool call")
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
        recommended_specialists=plan_args.get("recommended_specialists", [])
    )
```

### Fallback Plan

All error paths produce a valid `ContextPlan` with empty actions:

```python
def _fallback_plan(self, reason: str) -> Dict[str, Any]:
    fallback = ContextPlan(reasoning=f"Triage fallback: {reason}")
    return {
        "messages": [AIMessage(content=f"[Triage] {reason}")],
        "artifacts": {"context_plan": fallback.model_dump()},
        "scratchpad": {"triage_reasoning": fallback.reasoning, "recommended_specialists": []}
    }
```

Empty actions means `check_triage_outcome()` routes directly to Router. The system never stalls on a Triage failure — it falls through to Router with degraded (but functional) state.

---

## What Triage Does NOT Do

| Capability | Triage | Who Does It |
|------------|--------|-------------|
| Execute context actions | No | Facilitator |
| Route to specialists | No | Router (reads Triage's recommendation) |
| Create execution plans | No | SA (entry point: task_plan; MCP: project_plan, exit_plan) |
| Accumulate context | No | Facilitator (sole context writer) |
| Run on retry | No | Runs once; context_plan persists for Facilitator |
| Enforce routing | No | Recommendations are advisory; Router decides |
| Write user_request | No | state_factory.py writes it at initialization |

---

## Triage Ticket vs. Task Plan (#171)

Triage produces a **ticket**, not a plan. In real-world triage (medical, IT, support), triage outputs a classification and routing decision — the specialist makes the plan.

| Artifact | What It Is | Schema | Producer |
|----------|-----------|--------|----------|
| `task_plan` | System's theory of user intent | SystemPlan | SA (entry point, runs before Triage) |
| `context_plan` | Triage ticket: classification + routing + prep | ContextPlan | Triage (LLM call) |

SA runs first as the graph entry point, producing `task_plan`. Triage runs second, with the benefit of that plan already in state. Triage classifies and routes — it doesn't plan.

### Plan Hierarchy

The `task_plan` is the master plan. Specialist-specific plans derive from it:

```
SA (entry point) → task_plan (artifacts)
    |
Triage → context_plan / triage ticket (artifacts)
    |
    ├── PD calls SA MCP → project_plan (PD-specific steps)
    ├── EI calls SA MCP → exit_plan (verification of task_plan)
    └── WebBuilder calls SA MCP → system_plan (web implementation, #172)
```

All plans are write-once, read-many. The `task_plan` persists across retries.

See [SYSTEMS_ARCHITECT.md](./SYSTEMS_ARCHITECT.md) for the plan-first architecture and SA's dual role (entry point + MCP service).

---

## Graph Classification

Triage is the **second node** in the entry pipeline, wired by `ContextEngineeringSubgraph` ([context_engineering.py](../../app/src/workflow/subgraphs/context_engineering.py)):

```
SA (entry_point) → Triage → [Facilitator] → Router
```

- SA → Triage is an unconditional edge (SA always hands off to Triage)
- Triage → Facilitator/Router is a conditional edge via `check_triage_outcome()`
- Triage is excluded from Router's specialist menu (TRIAGE_INFRASTRUCTURE)
- Triage is excluded from its own specialist roster (can't recommend itself)
- Triage is excluded from hub-and-spoke edges (subgraph-managed via `get_excluded_specialists()`)

---

## Configuration

### Specialist Registration (config.yaml)

```yaml
workflow:
  entry_point: "systems_architect"   # SA is the entry point (#171)

specialists:
  triage_architect:
    type: "llm"
    prompt_file: "triage_architect_prompt.md"
    description: "Analyzes the user's request and creates a structured 'ContextPlan'..."
    tags: ["planning", "context_engineering"]
```

The `tags` are significant: Router uses them to identify Triage as a planning specialist, ensuring its recommendations are treated as advisory rather than dependency requirements.

### Dynamic Prompt Assembly

Unlike other specialists whose prompts are static, Triage's system prompt is assembled at startup by `GraphBuilder._configure_triage()` ([graph_builder.py:429-484](../../app/src/workflow/graph_builder.py#L429-L484)):

1. Load base prompt from `triage_architect_prompt.md`
2. Compute exclusions (MCP_ONLY + INTERNAL_ONLY + subgraph-managed + config-excluded + self)
3. Filter to `type: "llm"` specialists only
4. Append specialist names + descriptions to prompt

This ensures Triage can only recommend specialists that actually exist in this configuration.

---

## Archive Forensics

### Verify Triage Ran

```bash
# Check routing history — systems_architect is [0], triage_architect should be [1]
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history[0:2]'

# Check context_plan artifact
unzip -p ./logs/archive/run_*.zip final_state.json | jq '.artifacts.context_plan'
```

### Check What Triage Recommended

```bash
# See reasoning and recommended specialists
unzip -p ./logs/archive/run_*.zip final_state.json | \
  jq '{reasoning: .artifacts.context_plan.reasoning, recommended: .artifacts.context_plan.recommended_specialists, actions: (.artifacts.context_plan.actions | length)}'
```

### Verify Router Respected (or Overrode) Recommendation

```bash
# Compare triage recommendation vs actual routing
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'
# If routing_history[2] (after triage, facilitator) != recommended_specialists[0], Router overrode Triage
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
| [triage_architect_prompt.md](../../app/prompts/triage_architect_prompt.md) | Base system prompt (action types, routing heuristics, examples) |
| [context_schema.py](../../app/src/interface/context_schema.py) | `ContextPlan`, `ContextAction`, `ContextActionType` schemas |
| [graph_builder.py](../../app/src/workflow/graph_builder.py) | `_configure_triage()` dynamic prompt assembly (lines 429-484) |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_triage_outcome()` routing gate (lines 34-68) |
| [state_factory.py](../../app/src/graph/state_factory.py) | `user_request` artifact initialization (line 70) |
| [facilitator_specialist.py](../../app/src/specialists/facilitator_specialist.py) | Primary consumer of `context_plan` |
| [router_specialist.py](../../app/src/specialists/router_specialist.py) | Consumer of `recommended_specialists` (lines 202-290) |
| [test_triage_architect.py](../../app/tests/unit/test_triage_architect.py) | Unit tests (plan generation, fallbacks, blind triage) |
| [test_triage_routing_flow.py](../../app/tests/integration/test_triage_routing_flow.py) | Integration test (end-to-end routing validation) |

---

## Summary

The TriageArchitect is the **classifier and routing advisor** that:

1. Receives the request from SA (which has already produced `task_plan`)
2. Makes one LLM call with forced tool use to produce a `ContextPlan` (triage ticket: actions + reasoning + recommended specialists)
3. Routes to Facilitator (if actions exist) or directly to Router (if no context gathering needed)
4. Provides advisory specialist recommendations that Router may follow or override
5. Runs exactly once per request — its `context_plan` artifact persists across retries for Facilitator to re-read

Triage answers **"what context do we need?"** and **"who should do the work?"** It does not answer **"how should the work be done?"** — that's SA's job via `task_plan`.
