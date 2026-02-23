# Systems Architect Briefing: Intent Capture and Plan-First Execution in LAS

**Purpose:** Technical briefing on the Systems Architect's dual role as planning node and MCP planning service.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-23 (ADR-045: fork-aware verification plans; #199: Triage→SA pipeline flip; #173: acceptance_criteria; #217: SA fail-fast conditional edge)

---

## Executive Summary

The **Systems Architect (SA)** is an LLM-based planning specialist with a **dual role**:

1. **Planning node** — second in the entry pipeline (after Triage PASS). Produces `task_plan` (the system's theory of user intent), then hands off to Facilitator.
2. **MCP planning service** — called by other specialists to produce narrower, purpose-specific plans (exit verification, web implementation, etc.).

Key characteristics:
- **LLM-based planner** — calls the model once to produce a structured `SystemPlan` (with `acceptance_criteria`, #173)
- **Second in pipeline (#199)** — Triage → SA → Facilitator → Router → Specialist. SA only runs after Triage PASS.
- **MCP service** — also accessible via `mcp_client.call("systems_architect", "create_plan", ...)`
- **Shared `_generate_plan()` core** — same logic serves both pipeline execution and MCP interface
- **Plan-first principle** — specialists that do multi-step work should call SA before starting tool loops

---

## Dual Role: Entry Point + MCP Service

### Why Both?

SA was originally MCP-only (#129): specialists called it when they needed a plan, Router never saw it. #171 added SA as the entry point. #199 then flipped the pipeline: Triage runs first as an ACCEPT/REJECT gate, SA runs second only after Triage PASS. This means rejection happens before SA invests an LLM call on planning.

Now **every accepted request gets a `task_plan` before context gathering or routing happens**. Facilitator, Router, and all downstream specialists benefit from this intent capture.

The MCP service remains for **specialist-specific plans** that need narrower focus:

| Role | Pipeline Node | MCP Service |
|------|-------------|-------------|
| **Trigger** | Every accepted request (after Triage PASS) | On-demand by specialists |
| **Context** | User request + gathered_context | Specialist-tailored context string |
| **Output** | `artifacts["task_plan"]` | `artifacts[caller_specified_key]` |
| **Purpose** | System's theory of user intent | Specialist's execution/verification plan |
| **Runs** | Once per request (guard: `if not task_plan`) | Once per specialist (guard: `if not plan`) |

### Pipeline Node Flow (#199)

```
TriageArchitect (ACCEPT/REJECT gate)
    |
    [PASS]
    ▼
SystemsArchitect._execute_logic()
    |
    ├── Guard: if task_plan already exists → pass through (retry path)
    ├── _get_enriched_messages(state) → includes gathered_context if available
    └── _generate_plan(messages) → SystemPlan (with acceptance_criteria)
    |
    ▼
artifacts["task_plan"] = plan.model_dump()
    |
    ▼
check_sa_outcome (#217)
    |
    ├── task_plan EXISTS → Facilitator (assembles gathered_context) → Router → Specialist
    └── task_plan MISSING (SA failed) → END with termination_reason
```

### MCP Service Flow

```
Specialist needs a plan
    |
    ├── Guard: if plan already exists → skip
    └── mcp_client.call("systems_architect", "create_plan",
            context="tailored context string",
            artifact_key="exit_plan")
    |
    ▼
artifacts["exit_plan"] = plan.model_dump()
```

---

## SystemPlan Schema

```python
# From schemas/_orchestration.py
class SystemPlan(BaseModel):
    plan_summary: str                    # Concise one-sentence summary
    required_components: List[str]       # Technologies, libraries, assets needed
    execution_steps: List[str]           # Detailed sequential steps
    acceptance_criteria: str              # Observable outcomes defining "done" (#173, #216: required, min 30 chars)
```

The `acceptance_criteria` field (#173) provides externally observable outcomes — what the completed end state looks like. **Criteria must be verifiable from end-state alone** (#211): EI is a final-state-only observer that cannot see prior state, cannot track transitions, and cannot distinguish "original" files from specialist-created ones. The SA prompt enforces this with a contrastive BAD/GOOD example and prohibits transition language ("moved," "created from," "original"). EI feeds `acceptance_criteria` to SA when generating `exit_plan` for verification.

SA's system prompt ([systems_architect_prompt.md](../../app/prompts/systems_architect_prompt.md)) instructs the model to produce this exact structure. The prompt includes an example JSON output to ground the format.

The same schema serves all plan variants — `task_plan`, `exit_plan`, `system_plan`, `project_plan`. The caller controls the artifact key and context; SA always produces a SystemPlan.

---

## The Plan Hierarchy

`task_plan` is the master plan — the system's best understanding of what the user wants. Specialist-specific plans derive from it:

```
Triage (entry gate) → triage_actions / triage_reasoning in scratchpad (ACCEPT/REJECT, not a SystemPlan)
    |
SA (planning) → task_plan (with acceptance_criteria, #173)
    |
    ├── PD calls SA MCP → project_plan (filesystem execution steps)
    ├── EI calls SA MCP → exit_plan (verification of task_plan + acceptance_criteria)
    └── WebBuilder calls SA MCP → system_plan (web implementation, #172)
```

All plans are **write-once, read-many**. Each consumer uses a guard:

```python
# Entry point (systems_architect.py:50)
existing_plan = state.get("artifacts", {}).get("task_plan")
if existing_plan:
    return {"messages": [...]}  # pass through

# EI consumer (exit_interview_specialist.py:97)
exit_plan = artifacts.get("exit_plan")
if not exit_plan and self.mcp_client:
    result = self.mcp_client.call("systems_architect", "create_plan", ...)

# WebBuilder consumer (web_builder.py:32)
system_plan = artifacts.get("system_plan")
if not system_plan and self.mcp_client:
    plan_result = self.mcp_client.call("systems_architect", "create_plan", ...)
```

Plans persist across retries. On retry, the guard sees the existing plan and skips re-planning.

---

## MCP Interface

### `create_plan(context, artifact_key)`

```python
def create_plan(self, context: str, artifact_key: str) -> dict:
    """
    Args:
        context: What to plan for (user request, gathered context, verification scope)
        artifact_key: Artifact slot to write the plan to (e.g., "exit_plan", "project_plan")
    Returns:
        {"artifacts": {artifact_key: plan.model_dump()}}
    """
```

The `artifact_key` parameter allows different consumers to store plans in different slots:
- EI writes to `"exit_plan"`
- WebBuilder writes to `"system_plan"` (#172: should use `task_plan` as context)
- PD should write to `"project_plan"` (not yet implemented)

### Registration

SA registers itself via `register_mcp_services()`:

```python
def register_mcp_services(self, registry: 'McpRegistry'):
    registry.register_service(self.specialist_name, {
        "create_plan": self.create_plan,
    })
```

---

## Current Consumers

### Pipeline Node: task_plan (Every Accepted Request)

SA runs as the second graph node (after Triage PASS) on every accepted request. It:
1. Reads user messages (enriched with gathered_context if available)
2. Produces a `task_plan` capturing the system's theory of user intent (with `acceptance_criteria`)
3. Writes `artifacts["task_plan"]`
4. Hands off to Facilitator via `check_sa_outcome` (#217: conditional — routes to END if task_plan missing)

```python
# systems_architect.py:47-76
def _execute_logic(self, state: dict) -> Dict[str, Any]:
    existing_plan = state.get("artifacts", {}).get("task_plan")
    if existing_plan:
        return {"messages": [...]}  # pass through on retry

    messages = self._get_enriched_messages(state)
    plan = self._generate_plan(messages)
    return {
        "messages": [new_message],
        "artifacts": {"task_plan": plan.model_dump()},
    }
```

### Exit Interview: Verification Plan

EI calls SA with a verification-focused context (#115). Crucially, EI passes its **full tool inventory** (including `fork`) via `available_tools`, so SA constrains verification steps to EI's actual capabilities:

```python
# exit_interview_specialist.py — _ensure_exit_plan()
verification_tools = [
    {"name": name, "description": tool_def.description}
    for name, tool_def in self._build_tools().items()
    if name != "DONE"
]  # Includes fork since ADR-045

result = self.mcp_client.call(
    "systems_architect", "create_plan",
    context=verification_context,
    artifact_key="exit_plan",
    available_tools=verification_tools,
)
```

SA's prompt includes guidance for verification plans (ADR-045): when fork is in the tool inventory and the task involves N independent items, SA recommends fork-based verification instead of sequential file reads. This prevents EI's context death spiral (33K+ tokens observed in production).

EI then formats the `exit_plan` into its evaluation prompt so the LLM can verify completion against specific criteria.

### WebBuilder: Implementation Plan

WebBuilder calls SA when no `system_plan` exists in artifacts:

```python
# web_builder.py:32-51
system_plan = artifacts.get("system_plan")
if not system_plan and hasattr(self, 'mcp_client') and self.mcp_client:
    plan_result = self.mcp_client.call(
        "systems_architect",
        "create_plan",
        context=user_request,
        artifact_key="system_plan"
    )
    system_plan = plan_result.get("artifacts", {}).get("system_plan")
```

WebBuilder then **prepends the plan to its LLM messages** so the model sees the plan first.

> **#172:** WebBuilder should use `task_plan` as context for its SA call and potentially rename its artifact.

### Project Director: NOT YET IMPLEMENTED

**PD currently calls no planning service.** This is the root cause of the "reads files over and over" problem identified in #170 discussion:

1. PD starts its react_step loop with only `gathered_context` (which has a directory listing but no strategy)
2. The model reads every file to understand contents (burns iteration budget)
3. Hits `max_iterations` before writing anything
4. On retry, there are no write operations to extract knowledge from

**With an SA call**, PD would start with a `project_plan` like:
```json
{
    "plan_summary": "Categorize 13 files into topic subfolders based on content",
    "required_components": ["filesystem access", "content classification"],
    "execution_steps": [
        "List directory to enumerate files",
        "Read each file to determine topic category",
        "Create category subdirectories (animals, plants, technology, etc.)",
        "Move each file to its category directory",
        "Verify all files moved by listing source and destination directories"
    ]
}
```

The model would follow this methodically instead of flailing. The plan also gives EI concrete steps to verify against.

---

## The Plan-First Pattern

The architectural principle: **every ReAct specialist should work off a plan, procedurally enforced.**

The plan is:
- **Not routed** — the specialist calls SA via MCP, not the other way around
- **Not optional** — specialists should call SA before starting tool loops
- **Tailored to consumer** — each specialist provides context appropriate to its needs
- **Stored as artifact** — persists across retries, available to EI for verification

### What a Plan Provides

| Without Plan | With Plan |
|---|---|
| Model decides what to do each iteration | Model follows structured steps |
| No success criteria | `execution_steps` define what "done" looks like |
| EI has no verification checklist | EI can verify against `exit_plan` |
| Retry loses all strategy | Plan persists in artifacts across retries |
| Iteration budget spent on reconnaissance | Reconnaissance is one step in a known sequence |

### Relationship to Facilitator and Triage

SA, Triage, and Facilitator serve complementary roles in the entry pipeline:

| | Triage | SA | Facilitator |
|---|---|---|---|
| **What** | Gate (ACCEPT/REJECT) | Strategy (steps, components, criteria) | Context (facts, observations, prior work) |
| **Schema** | `ContextPlan` (wire format -> scratchpad) | `SystemPlan` (with `acceptance_criteria`) | `gathered_context` (string) + `accumulated_work` (list) |
| **When** | Once (first in pipeline, #199) | Once (second, after Triage PASS; once per specialist via MCP) | Before every specialist invocation |
| **How** | LLM call → structured output (`output_model_class`) | LLM call → structured JSON | Procedural MCP orchestrator (no LLM) |
| **On retry** | Ticket persists, no re-triage | Plan persists, no re-planning | Rebuilds fresh from current state |

Together they give a specialist **what to do** (SA), **what background context to gather** (Triage), and **what is known** (Facilitator).

---

## Graph Classification

SA is classified as `CORE_INFRASTRUCTURE` in [specialist_categories.py](../../app/src/workflow/specialist_categories.py):

```python
CORE_INFRASTRUCTURE: frozenset = frozenset([
    CoreSpecialist.ROUTER.value,
    CoreSpecialist.ARCHIVER.value,
    CoreSpecialist.END.value,
    CoreSpecialist.EXIT_INTERVIEW.value,
    "systems_architect",  # Issue #171
])
```

This means:
- SA **is a graph node** — added by the ContextEngineeringSubgraph
- Triage → SA is a conditional edge (only on PASS) via `check_triage_outcome()` (#199)
- SA → Facilitator is a conditional edge via `check_sa_outcome()` (#217: routes to END if `task_plan` missing)
- SA **is excluded from Router's menu** — it's infrastructure, not a task-execution specialist
- SA **is excluded from hub-and-spoke edges** — has dedicated subgraph wiring
- SA **is also registered in MCP** — specialists can still call `create_plan()` for narrower plans

---

## Configuration

### Specialist Registration (config.yaml)

```yaml
workflow:
  entry_point: "systems_architect"  # SA is the entry point (#171)

specialists:
  systems_architect:
    is_enabled: true
    type: "structured"
    prompt_file: "systems_architect_prompt.md"
    llm_config: "model_name_here"
```

SA needs an `llm_config` because it makes LLM calls (unlike Facilitator which is procedural).

### Dependency Injection

- `llm_adapter` — makes the planning LLM call
- Registered in MCP registry at startup via `register_mcp_services()`
- Consumers access via `self.mcp_client.call("systems_architect", "create_plan", ...)`

---

## Key Files

| File | Purpose |
|------|---------|
| [systems_architect.py](../../app/src/specialists/systems_architect.py) | SA implementation — `_execute_logic()` (entry point), `create_plan()` (MCP), `_generate_plan()` (shared core) |
| [systems_architect_prompt.md](../../app/prompts/systems_architect_prompt.md) | System prompt with SystemPlan JSON example |
| [_orchestration.py](../../app/src/specialists/schemas/_orchestration.py) | `SystemPlan` Pydantic schema |
| [specialist_categories.py](../../app/src/workflow/specialist_categories.py) | `CORE_INFRASTRUCTURE` classification (#171) |
| [context_engineering.py](../../app/src/workflow/subgraphs/context_engineering.py) | Triage → SA → Facilitator → Router edge wiring (#199, #217) |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `check_sa_outcome()` conditional edge (#217) |
| [web_builder.py](../../app/src/specialists/web_builder.py) | Consumer: implementation plan (lines 32-51) |
| [exit_interview_specialist.py](../../app/src/specialists/exit_interview_specialist.py) | Consumer: verification plan with fork-aware tool inventory (ADR-045) |
| [project_director.py](../../app/src/specialists/project_director.py) | NOT YET a consumer — missing SA call is the root cause of aimless tool chaining |

---

## Summary

The Systems Architect has a **dual role** in LAS:

1. **Planning node** — second in pipeline (after Triage PASS, #199). Captures intent as `task_plan` with `acceptance_criteria` (#173) before context gathering or routing. This is the system's theory of what the user wants.
2. **MCP service** — called by specialists for narrower, purpose-specific plans (`exit_plan`, `system_plan`, `project_plan`). Planning is procedurally enforced, not routed.

All plans use the same `SystemPlan` schema (with `acceptance_criteria`) and share the `_generate_plan()` core. Plans are write-once, read-many artifacts that persist across retries.

**Architectural principle:** SA captures intent after Triage validation (task_plan) and provides specialist-specific strategy on demand (MCP). Every specialist with ReAct capability should call SA before starting its tool loop.

See [TRIAGE.md](./TRIAGE.md) for how the triage ticket relates to task_plan, and [FACILITATOR.md](./FACILITATOR.md) for how context complements strategy.
