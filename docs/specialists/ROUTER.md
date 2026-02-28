# Router Briefing: Turn-by-Turn Specialist Selection in LAS

**Purpose:** Technical briefing on the RouterSpecialist's role as the central routing hub.
**Audience:** Developers, architects, or AI agents integrating with or extending LAS.
**Updated:** 2026-02-25 (#219: dedup and cap specialist selection lists; ADR-077: signal processor replaces classify_interrupt; ADR-CORE-016: menu filter pattern)

---

## Executive Summary

The **Router** is the **CPU/scheduler** of the LAS orchestration system. It makes turn-by-turn routing decisions, directing each request to the specialist best suited to handle it. Every specialist execution eventually returns to Router for the next decision.

Key characteristics:
- **Hub of hub-and-spoke** — all non-terminal specialists route back through Router
- **Three routing paths** — deterministic (archive done), deterministic (trivial greeting), LLM-based (full specialist menu)
- **Enum-constrained output** — dynamic Pydantic model with `Literal` enum prevents open-weight models from generating approximate names
- **Context-aware menu filtering** — removes planning specialists after context is gathered, removes forbidden specialists on loop detection
- **Only specialist that increments turn_count** — bypasses SafeExecutor to preserve this invariant
- **Supports parallel fan-out** — can return a list of specialists for concurrent execution

---

## Where Router Fits in the Execution Flow

### First Pass (New Request)

```
User Request
    |
TriageArchitect (ACCEPT/REJECT gate)
    |
    [check_triage_outcome]
    |-- PASS  --> SystemsArchitect (task_plan) --[check_sa_outcome]--> Facilitator --> Router --> Specialist
    '-- CLARIFY --> EndSpecialist (reject with cause)
```

Router is the **first decision point** where `gathered_context` is available. The entry pipeline (Triage → SA → Facilitator) runs before Router, assembling context for an informed routing decision.

### Specialist Completion → Return to Router

```
Specialist (e.g., PD)
    |
    v
SignalProcessorSpecialist (ADR-077: procedural interrupt classification)
    |
    +-- No signals, no artifacts --> Router (continue workflow)
    +-- Artifacts present         --> ExitInterview (completion check)
    +-- max_iterations_exceeded   --> ExitInterview (BENIGN continuation)
    +-- stagnation_detected       --> InterruptEvaluator/ExitInterview (PATHOLOGICAL)
    +-- circuit_breaker           --> ExitInterview/END
```

### Terminal Specialists (Skip Signal Processor)

```
default_responder_specialist  --.
chat_specialist               --+--> check_task_completion --> END (skip EI, no success criteria)
tiered_synthesizer_specialist --'
```

### Exit Interview Retry Path

```
ExitInterview
    |
    +-- COMPLETE               --> END
    +-- INCOMPLETE             --> Facilitator (rebuild context) --> Router --> Specialist (retry)
    +-- INCOMPLETE + loop      --> END (abort with termination_reason)
```

---

## Router's Three Routing Paths

Router checks conditions in priority order. The first match wins.

### Path 1: Deterministic Archive Completion

```python
# router_specialist.py:467-471
if state.get("artifacts", {}).get("archive_report.md"):
    next_specialist_name = END
    routing_type = "deterministic_end"
```

If `archive_report.md` exists in artifacts, the workflow is complete. No LLM call needed.

### Path 2: Deterministic Trivial Request

```python
# router_specialist.py:472-477
elif self._is_trivial_request(state):
    next_specialist_name = "default_responder_specialist"
    routing_type = "deterministic_trivial"
```

Pre-LLM gate for a closed set of greetings and health checks. Checked against `user_request` (the original input, not conversation messages), so no prompt injection via conversation history can override this.

**Trivial inputs:** `hello`, `hi`, `hey`, `ping`, `pong`, `thanks`, `thank you`, `bye`, `goodbye`, `test`, `yo`, `sup`, `what's up`, `whats up`

**Trivial heuristic:** Single-word messages ≤15 characters with no question mark.

### Path 3: LLM-Based Routing

```python
# router_specialist.py:478-483
else:
    llm_decision = self._get_llm_choice(state)
    next_specialist_name = llm_decision["next_specialist"]
    routing_type = "llm_decision"
```

Full specialist selection with dynamic menu, context injection, and enum-constrained output schema. See [LLM Routing Decision](#llm-routing-decision-_get_llm_choice) below.

---

## LLM Routing Decision (`_get_llm_choice`)

The LLM path is a multi-stage pipeline with deterministic shortcuts at each stage.

### Stage 1: Specialist Menu Assembly

`_get_available_specialists()` applies three filters:

| Filter | Trigger | Effect |
|--------|---------|--------|
| Context-aware | `gathered_context` artifact exists | Removes `context_engineering`-tagged specialists (Triage, Facilitator) — their job is done |
| Menu filter (ADR-CORE-016) | `scratchpad.forbidden_specialists` set | Removes forbidden specialists (hard constraint, P=0). Set by InvariantMonitor on loop detection |
| Safety fallback | All specialists filtered out | Returns only END specialist (prevents hard crash) |

### Stage 2: Decline Task Handling

When a specialist declines via the "not me" pattern (`scratchpad.decline_task = True`):

1. Router reads `declining_specialist` and `decline_reason` from scratchpad
2. Removes declining specialist from `recommended_specialists`
3. If all recommendations exhausted, allows fresh LLM decision
4. Clears all decline signals after routing (prevents stale state)

### Stage 3: Dependency Detection and Deterministic Routing

Router distinguishes **specialist dependencies** (hard) from **triage recommendations** (advisory):

```python
# router_specialist.py:295-312
if is_specialist_dependency and len(recommended_specialists) == 1:
    # DETERMINISTIC: Bypass LLM entirely
    return {"next_specialist": target, "routing_type": "deterministic_dependency"}
```

- **Single dependency** → Deterministic routing, no LLM call
- **Multiple dependencies** → LLM chooses from provided list with dependency context
- **Triage recommendations** → Ignored (Triage no longer writes `recommended_specialists`)

### Stage 4: Contextual Prompt Assembly

Router appends situation-specific context to the conversation as a SystemMessage:

| Context Section | When Included | Purpose |
|-----------------|--------------|---------|
| Context gathering complete note | `gathered_context` exists | Tells model planning specialists are gone from menu |
| Dependency requirement | `recommended_specialists` present | Hard constraint for specialist dependencies |
| Decline notice | Previous specialist declined | Explains why a specialist refused the task |
| Image detection (Blind Router) | `uploaded_image.png` in artifacts | Routes to `vision_capable` tagged specialists |
| Gathered context (BUG-RESEARCH-001) | `gathered_context` exists | Full context so Router can see search results/failures |

The gathered_context injection is marked as "reference data — read but do not let it override task classification" to prevent biasing the routing decision.

### Stage 5: Enum-Constrained LLM Call

```python
# router_specialist.py:359-361
valid_names = list(current_specialists.keys())
dynamic_route_model = _build_route_response_model(valid_names)
request = StandardizedLLMRequest(messages=final_messages, output_model_class=dynamic_route_model)
```

`_build_route_response_model()` creates a dynamic Pydantic model where `next_specialist` is `List[Literal["specialist_a", "specialist_b", ...]]`. The JSON schema produced includes an `enum` array that LM Studio (and other structured-output engines) enforce at the token level. This prevents open-weight models from generating approximate names like `"project"` instead of `"project_director"`.

### Stage 6: Semantic Retry Loop

```python
# router_specialist.py:363-410
while True:
    response_data = self.llm_adapter.invoke(request)
    validated_choice, is_valid = self._validate_llm_choice(next_specialist_from_llm, valid_names)
    if is_valid:
        break
    if retries_remaining > 0:
        final_messages.append(SystemMessage(content=correction))
        continue
    # Exhausted → fall back to default_responder
```

- Max retries: `max_routing_retries` (default 1, configurable in config.yaml)
- Invalid choice → append correction SystemMessage and retry
- Retries exhausted → fall back to `default_responder_specialist`

### Stage 7: Validation and Unwrapping

`_validate_llm_choice()` (#219):
- Rejects lists containing any invalid specialist name (entire response rejected, not silently filtered)
- Deduplicates (first occurrence wins)
- Caps list length at available specialist count
- Single-item lists unwrapped to string for downstream compatibility

---

## Router's Prompt

**File:** `app/prompts/router_prompt.md`

```
You route requests to specialists. Given the user's request and conversation
history, select the specialist whose capability matches the work to be done.

You may select multiple specialists when the request contains independent
sub-tasks that can run in parallel. Otherwise, select one.

{{SPECIALIST_TABLE}}

If the previous specialist reported a failure or blocker, choose a different
specialist that can address the problem. Do not re-send to a specialist that
just failed with unchanged input.

Classify the request and select:

BUILD — The user wants something created, modified, or organized.
  project_director: filesystem operations, terminal commands, multi-step tool use
  web_builder: HTML, CSS, JavaScript, Gradio web interfaces

ANSWER — The user wants information, explanation, or reasoning about context.
  chat_specialist: questions, concepts, analysis of provided context

OBSERVE — The user wants external data fetched or examined.
  navigator_browser_specialist: interactive website browsing
  image_specialist: visual content analysis

GREET — Social input with no task (hello, thanks, ping, bye).
  default_responder_specialist
```

`{{SPECIALIST_TABLE}}` is replaced at graph build time with a dynamic table of all routable specialists and their descriptions. Built by `graph_builder._build_specialist_table()`.

---

## Graph Wiring

### Router Node Registration

```python
# graph_builder.py:500-503
if name == CoreSpecialist.ROUTER.value:
    workflow.add_node(name, instance.execute)  # DIRECT — no SafeExecutor
else:
    workflow.add_node(name, self.node_executor.create_safe_executor(instance))
```

Router bypasses SafeExecutor because:
1. **turn_count invariant** — only Router can increment `turn_count`. SafeExecutor strips `turn_count` from other specialists' state updates.
2. **Own observability** — Router implements tracing directly in `_execute_logic()` (set/clear specialist context, flush adapter traces, build turn trace, build timeline entry).

### Outbound Edges (Router → Specialists)

```python
# graph_builder.py:527
workflow.add_conditional_edges(
    router_name,
    self.orchestrator.route_to_next_specialist,
    destinations  # All specialists except Router itself and node-excluded specialists
)
```

`route_to_next_specialist()` in GraphOrchestrator reads `state.next_specialist` (set by Router's `_execute_logic`) and validates against `allowed_destinations`. It also handles:
- **Stabilization check** — circuit breaker override → EXIT_INTERVIEW
- **Loop detection** — unproductive routing loop → EXIT_INTERVIEW
- **Chat interception (CORE-CHAT-002)** — `chat_specialist` → parallel fan-out to `[progenitor_alpha, progenitor_bravo]` in tiered mode
- **Virtual coordinator (distillation)** — `distillation_specialist` → `distillation_coordinator_specialist`

### Inbound Edges (Specialists → Router)

Non-terminal specialists return to Router through the Signal Processor:

```
Specialist → SignalProcessor (unconditional edge)
SignalProcessor → route_from_signal() → routing_target
```

Signal Processor's priority chain:
1. Circuit breaker → EI/END
2. User abort → END
3. max_iterations_exceeded → EI (BENIGN)
4. stagnation_detected → IE/EI/Router (PATHOLOGICAL)
5. Artifacts present → EI (normal completion check)
6. No artifacts, no signals → **Router** (continue workflow)

When ExitInterview says INCOMPLETE, the retry path goes through Facilitator (to refresh `gathered_context`) before returning to Router.

### Specialists Excluded from Hub-and-Spoke

These specialists have special wiring and are NOT standard spoke nodes:

| Specialist | Why Excluded | Wired By |
|-----------|-------------|----------|
| `router_specialist` | Is the hub | Self (conditional edges to all destinations) |
| `archiver_specialist` | Terminal infrastructure | `end_specialist → END` |
| `end_specialist` | Graph terminator | `→ langgraph.END` |
| `exit_interview_specialist` | Completion gate | `after_exit_interview()` conditional edge |
| `signal_processor_specialist` | Interrupt classifier | Between specialist and routing decision |
| `systems_architect` | Entry pipeline | `context_engineering` subgraph |
| Subgraph internals | Managed by subgraph | e.g., progenitors, synthesizer, distillation nodes |

---

## Parallel Execution Support

Router can initiate parallel specialist execution by returning a list:

```python
# router_specialist.py:497-501
if isinstance(next_specialist_name, list) and len(next_specialist_name) > 1:
    parallel_tasks_update = next_specialist_name
```

**Scatter-Gather pattern:**
1. Router sets `parallel_tasks = ["specialist_a", "specialist_b"]`
2. LangGraph executes both in parallel
3. SafeExecutor's barrier logic: each specialist removes itself from `parallel_tasks` on completion
4. `check_task_completion()` checks `parallel_tasks`: if non-empty → END (terminate branch, wait); if empty → Router (all complete, aggregate)

Currently used for CORE-CHAT-002 tiered chat (progenitor_alpha + progenitor_bravo in parallel).

---

## State Updates

Router's `_execute_logic` returns:

```python
{
    "messages": [ai_message],              # Routing decision message
    "next_specialist": next_specialist,    # str or list[str]
    "turn_count": turn_count,              # Incremented (ONLY Router does this)
    "scratchpad": {
        "recommended_specialists": None,   # Consumed after routing
        "decline_task": None,              # Cleared
        "declining_specialist": None,
        "decline_reason": None,
        "router_decision": "...",          # Diagnostics for Thought Stream
    },
    "parallel_tasks": [...],               # Empty or list for fan-out
    "routing_history": [self.specialist_name],
    "llm_traces": [...],                   # Captured if LLM path was taken
    "state_timeline": [...],               # Boundary snapshot
}
```

Key signals consumed and cleared:
- `recommended_specialists` — consumed after routing decision
- `decline_task` / `declining_specialist` / `decline_reason` — cleared to prevent stale signals
- `im_decision` — cleared after timeline capture

---

## Error Handling and Fallbacks

### LLM Failure Cascade

```python
# router_specialist.py:150-162
def _handle_llm_failure(self):
    if DEFAULT_RESPONDER in specialist_map → route there
    elif ARCHIVER in specialist_map → route there
    else → route to END
```

### Validation Failure (Retries Exhausted)

After `max_routing_retries` invalid LLM responses → fall back to `default_responder_specialist`.

### Empty Specialist Menu

If all specialists filtered out by Menu Filter → return only END specialist as fallback.

### No next_specialist in State

If Router somehow didn't set `next_specialist` → `route_to_next_specialist()` routes to EXIT_INTERVIEW for completion check.

---

## What Router Does NOT Do

| Capability | Router | Who Does It |
|------------|--------|-------------|
| Execute tasks | No | Specialists (PD, WebBuilder, etc.) |
| Assemble context | No | Facilitator (sole context writer) |
| Classify prompt completeness | No | TriageArchitect (ACCEPT/REJECT gate) |
| Create execution plans | No | SA (task_plan) |
| Validate task completion | No | ExitInterview |
| Classify interrupt signals | No | SignalProcessor (ADR-077) |
| Produce artifacts | No | Router produces no artifacts |
| Read files or call MCP | No | Pure routing decisions only |

---

## Router Configuration

### Graph Builder Configuration (`_configure_router`)

```python
# graph_builder.py:404-434
def _configure_router(self, specialists, all_configs):
    # 1. Load base prompt
    base_prompt = load_prompt("router_prompt.md")

    # 2. Collect exclusions (subgraph + config-driven + infrastructure)
    exclusions = SpecialistCategories.get_router_exclusions(
        subgraph_exclusions, config_exclusions
    )

    # 3. Build available specialists (all minus excluded)
    available = {name: config for name, config in all_configs.items()
                 if name not in exclusions}

    # 4. Inject specialist map into Router instance
    router_instance.set_specialist_map(available)

    # 5. Build dynamic specialist table and replace {{SPECIALIST_TABLE}}
    # 6. Create adapter with assembled system prompt
```

Router is configured AFTER subgraphs are initialized because router exclusions dynamically query subgraph exclusions.

### Specialist Registration (config.yaml)

```yaml
specialists:
  router_specialist:
    type: "llm"
    prompt_file: "router_prompt.md"
    description: "Routes requests to appropriate specialists"
    max_routing_retries: 1
    tags: []  # No tags — Router is infrastructure, not a spoke
```

### Specialist Categories

```python
# specialist_categories.py
CORE_INFRASTRUCTURE = frozenset([
    "router_specialist",        # Is the hub
    "archiver_specialist",      # Terminal
    "end_specialist",           # Terminal
    "exit_interview_specialist", # Completion gate
    "signal_processor_specialist", # Interrupt classifier
    "systems_architect",        # Entry pipeline
])
```

Router is in CORE_INFRASTRUCTURE and excluded from:
- Its own tool schema (cannot route to itself)
- Hub-and-spoke edges (is the hub, not a spoke)
- Triage's recommendations (infrastructure, not user-routable)

---

## Archive Forensics

### Verify Router Ran and What It Decided

```bash
# Check routing history — router_specialist appears after entry pipeline
unzip -p ./logs/archive/run_*.zip manifest.json | jq '.routing_history'

# Check Router's LLM trace (only present on LLM path, not deterministic paths)
unzip -p ./logs/archive/run_*.zip llm_traces.jsonl | grep router_specialist | jq .
```

### Check Routing Type

```bash
# See routing decision type in messages
unzip -p ./logs/archive/run_*.zip final_state.json | \
  jq '[.messages[] | select(.name == "router_specialist") | .additional_kwargs]'
```

Each Router message includes `routing_decision` (the target specialist) and `routing_type` (`deterministic_end`, `deterministic_trivial`, `deterministic_dependency`, or `llm_decision`).

### Check Menu Filter State

```bash
# See if forbidden_specialists was active
unzip -p ./logs/archive/run_*.zip final_state.json | \
  jq '.scratchpad.forbidden_specialists'
```

---

## Key Files

| File | Purpose |
|------|---------|
| [router_specialist.py](../../app/src/specialists/router_specialist.py) | RouterSpecialist implementation, RouteResponse schema, trivial detection, LLM routing |
| [router_prompt.md](../../app/prompts/router_prompt.md) | System prompt with `{{SPECIALIST_TABLE}}` placeholder |
| [graph_builder.py](../../app/src/workflow/graph_builder.py) | `_configure_router()` prompt assembly, node registration (SafeExecutor bypass), hub-and-spoke edge wiring |
| [graph_orchestrator.py](../../app/src/workflow/graph_orchestrator.py) | `route_to_next_specialist()`, `check_task_completion()`, `after_exit_interview()`, loop detection |
| [specialist_categories.py](../../app/src/workflow/specialist_categories.py) | CORE_INFRASTRUCTURE, router exclusions, hub-spoke exclusions |
| [signal_processor_specialist.py](../../app/src/specialists/signal_processor_specialist.py) | Interrupt classification, routing_target output (sits between specialists and Router) |
| [node_executor.py](../../app/src/workflow/node_executor.py) | SafeExecutor (Router bypasses), turn_count stripping, parallel barrier logic |
| [helpers.py](../../app/src/specialists/helpers.py) | `create_decline_response()` for "not me" pattern |

---

## Summary

The Router is the **hub of the hub-and-spoke graph** that:

1. Makes turn-by-turn routing decisions after Facilitator assembles context
2. Has three paths: deterministic (archive done / trivial greeting) and LLM-based (full specialist menu)
3. Enforces routing constraints at the token level via enum-constrained JSON schema output
4. Filters its specialist menu dynamically: context-aware removal of planning specialists, menu filter for loop recovery, decline handling
5. Is the only specialist that increments `turn_count` — bypasses SafeExecutor to preserve this invariant
6. Supports parallel fan-out (list of specialists) with scatter-gather barrier logic
7. Clears consumed signals (recommendations, declines) after each routing decision to prevent stale state

Router answers **"who should do the work next?"** It does not answer **"should we accept this request?"** (Triage), **"what context do they need?"** (Facilitator), or **"is the work done?"** (ExitInterview).
