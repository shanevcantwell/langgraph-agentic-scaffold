# Triage Architect Briefing: Intent Classification and Context Planning in LAS

**Purpose:** Technical briefing on the TriageArchitect specialist's role as the classifier and context planner.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-12 (context_plan artifact eliminated — actions move to scratchpad)

---

## Executive Summary

The **TriageArchitect** produces a **triage ticket** — classification and intake prep actions. It answers one question: **what context is needed** (actions for Facilitator to execute).

Triage is NOT the entry point. SA runs first to produce a `task_plan` (the system's theory of user intent), then Triage classifies with the benefit of that plan.

Key characteristics:
- **Second in entry pipeline** — SA → Triage → [Facilitator] → Router → Specialist (#171)
- **LLM-based classifier** — makes one LLM call with forced tool use to produce a structured `ContextPlan` (triage ticket)
- **Does not execute** — Triage classifies and plans context-gathering; it never gathers context or does work itself
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
SystemsArchitect (entry point, #171)
    writes artifacts["task_plan"]  -- system's theory of user intent
    |
    v
TriageArchitect (LLM: classifies intent, creates triage ticket)
    |
    +-- scratchpad["triage_reasoning"] = reasoning string
    +-- scratchpad["triage_actions"]   = [{type, target, description}, ...]
    |
    v
check_triage_outcome()  [graph_orchestrator.py]
    |
    +-- actions present?  -> facilitator_specialist  -> Router -> Specialist
    +-- ask_user only?    -> end_specialist (reject with cause, #179)
    +-- no actions?       -> router_specialist (direct)
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

`ContextPlan` is a **wire format** for Triage's forced tool call — the LLM must produce this structure. The plan is NOT stored as an artifact. Instead, its fields are decomposed to scratchpad.

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

**Tool schema** = `ContextPlan` as a forced tool call:
```python
request = StandardizedLLMRequest(
    messages=messages,
    tools=[ContextPlan],
    force_tool_call=True   # LLM MUST produce a ContextPlan, no free-text
)
```

`force_tool_call=True` means the LLM has no option to respond without producing a ContextPlan. The tool schema defines `actions` and `reasoning` fields via Pydantic -> OpenAI function calling format.

---

## Routing Decision: check_triage_outcome()

`check_triage_outcome()` in [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) implements a three-way gate:

```python
def check_triage_outcome(self, state: GraphState) -> str:
    triage_actions = state.get("scratchpad", {}).get("triage_actions", [])

    if triage_actions:
        # #179: Ask-user-only plan = underspecified prompt -> reject
        ask_user_count = sum(1 for a in triage_actions if a.get("type") == "ask_user")
        other_count = len(triage_actions) - ask_user_count
        if other_count == 0 and ask_user_count > 0:
            return CoreSpecialist.END.value   # Reject with cause
        return "facilitator_specialist"       # Context gathering needed

    return CoreSpecialist.ROUTER.value        # No context needed
```

This means:
- **Simple greeting** ("hello") -> empty actions -> straight to Router
- **File task** ("sort these files") -> `LIST_DIRECTORY` action -> Facilitator gathers context first -> then Router
- **Research task** ("find current GPU prices") -> `RESEARCH` action -> Facilitator does web search -> then Router
- **Ambiguous request** ("help me with it") -> ask_user only -> EndSpecialist formats rejection (#179)

The decision is purely structural (are there actions? what kind?) not semantic (what kind of task?). Specialist selection is Router's job.

---

## How Triage's Output Flows Downstream

### Path 1: Facilitator Reads triage_actions

Facilitator reads `scratchpad["triage_actions"]` and:

1. Parses each action dict into a `ContextAction` for type-safe dispatch
2. Iterates through actions, calling MCP services for each (RESEARCH -> web search, READ_FILE -> filesystem, etc.)
3. Assembles results into `gathered_context` artifact
4. Task Strategy comes from `task_plan.plan_summary` (SA's intent capture), not from Triage reasoning

See [FACILITATOR.md](./FACILITATOR.md) for the full context assembly story.

### Path 2: triage_actions Persists Across Retries

On retry (EI said INCOMPLETE), Facilitator re-reads `scratchpad["triage_actions"]` to:
- Re-execute plan actions (e.g., re-list directory to see current state)
- Add EI feedback and trace knowledge alongside the action results

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

Empty actions means `check_triage_outcome()` routes directly to Router. The system never stalls on a Triage failure — it falls through to Router with degraded (but functional) state.

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

## Triage Ticket vs. Task Plan (#171)

Triage produces a **ticket**, not a plan. In real-world triage (medical, IT, support), triage outputs a classification and routing decision — the specialist makes the plan.

| Output | What It Is | Schema | Producer |
|--------|-----------|--------|----------|
| `task_plan` | System's theory of user intent | SystemPlan | SA (entry point, runs before Triage) |
| `triage_actions` / `triage_reasoning` | Triage ticket: what context to gather | ContextPlan (wire format) | Triage (LLM call) |

SA runs first as the graph entry point, producing `task_plan`. Triage runs second, with the benefit of that plan already in state. Triage classifies what context is needed — it doesn't plan the task or select specialists.

### Plan Hierarchy

The `task_plan` is the master plan. Specialist-specific plans derive from it:

```
SA (entry point) -> task_plan (artifacts)
    |
Triage -> triage_actions / triage_reasoning (scratchpad)
    |
    +-- PD calls SA MCP -> project_plan (PD-specific steps)
    +-- EI calls SA MCP -> exit_plan (verification of task_plan)
    +-- WebBuilder calls SA MCP -> system_plan (web implementation, #172)
```

All plans are write-once, read-many. The `task_plan` persists across retries.

See [SYSTEMS_ARCHITECT.md](./SYSTEMS_ARCHITECT.md) for the plan-first architecture and SA's dual role (entry point + MCP service).

---

## Graph Classification

Triage is the **second node** in the entry pipeline, wired by `ContextEngineeringSubgraph` ([context_engineering.py](../../app/src/workflow/subgraphs/context_engineering.py)):

```
SA (entry_point) -> Triage -> [Facilitator] -> Router
```

- SA -> Triage is an unconditional edge (SA always hands off to Triage)
- Triage -> Facilitator/Router/END is a conditional edge via `check_triage_outcome()`
- Triage is excluded from Router's specialist menu (TRIAGE_INFRASTRUCTURE)
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

The `tags` are significant: they identify Triage as a planning specialist for graph wiring purposes.

---

## Archive Forensics

### Verify Triage Ran

```bash
# Check routing history -- systems_architect is [0], triage_architect should be [1]
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history[0:2]'
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

The TriageArchitect is the **classifier and context planner** that:

1. Receives the request from SA (which has already produced `task_plan`)
2. Makes one LLM call with forced tool use to produce a `ContextPlan` wire format (actions + reasoning)
3. Writes actions and reasoning to scratchpad (no artifact)
4. Routes to Facilitator (if actions exist), END (if ask_user only, #179), or Router (if no context needed)
5. Runs exactly once per request — scratchpad entries persist across retries for Facilitator to re-read

Triage answers **"what context do we need?"** It does not answer **"who should do the work?"** (Router) or **"how should the work be done?"** (SA via `task_plan`).
