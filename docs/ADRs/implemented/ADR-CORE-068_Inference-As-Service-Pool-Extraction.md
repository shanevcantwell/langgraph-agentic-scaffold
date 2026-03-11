# ADR-CORE-068: Inference as Service — Pool Extraction and Service Boundary

**Status**: IMPLEMENTED
**Date**: 2026-02-08
**Implemented**: 2026-02-12
**Subsumes**: ADR-CORE-067 (Adapter Convergence — Shared Pool Architecture)
**Relates to**:
- ADR-CORE-052 (Migration to Adapter-Registry Pattern for Tiered Chat)
- ADR-CORE-054 (Dispatcher Sync-Async Boundary)
- ADR-CORE-066 (Sleeptime Autonomous Orchestration — background evaluation)
- ADR-MCP-004 (LLM-Backed MCP Services — model-at-call-time pattern)
- prompt-prix ADR-006 (Adapter Owns Pool and Dispatcher)

---

## Context

### What ADR-067 Got Right and Wrong

ADR-067 correctly identified three problems with LAS's per-specialist adapter architecture:

1. **N adapters for N specialists** — no coordination between them
2. **No multi-server support** — each specialist hardwired to one `base_url`
3. **GraphBuilder bloat** — ~150 lines of per-specialist adapter wiring

ADR-067 proposed solving these by **porting** prompt-prix's `_ServerPool` and `_ConcurrentDispatcher` into LAS — copying ~280 lines of infrastructure into a new `app/src/llm/pool.py`.

This was the wrong mechanism. Porting creates a second copy of tested infrastructure with no structural guarantee that the copies stay synchronized. It's library thinking applied to a service boundary.

### The Three-Layer Separation

Cross-repo analysis revealed that what appeared to be "prompt-prix's adapter infrastructure" is actually three distinct layers with clean dependency arrows:

```
TOOLKIT        complete(), judge(), list_models(), react_step()...
               Thin functions that call get_adapter().stream_completion()

ADAPTERS       LMStudioAdapter, TogetherAdapter, HuggingFaceAdapter
               Each implements HostAdapter protocol independently

INFRASTRUCTURE ServerPool, ConcurrentDispatcher, ServerConfig
               Multi-GPU slot management, JIT-swap protection
               Internal to LMStudioAdapter ONLY — other adapters don't use it
```

The toolkit never sees infrastructure. Adapters are pluggable. Infrastructure is encapsulated inside specific adapter implementations. These boundaries already exist in the code — prompt-prix ADR-006 enforces exactly this separation.

### Why Repo Boundaries Matter

Convention-based boundaries ("don't import `_ServerPool` outside of `lmstudio.py`") are insufficient. Across sessions, AI assistants may "helpfully" blur abstraction layers — importing internal classes because they're convenient, coupling modules that should be independent. The violation isn't discovered until there's a week of disentanglement work.

A repo boundary makes violations structurally impossible. You cannot import from a module that isn't declared as a package dependency. `ModuleNotFoundError` is a harder wall than a code review comment. This is OO encapsulation abstracted to the product level.

### Decision Evolution: From MCP-Only to Hot/Cold Split

The cross-repo discussion initially converged on **MCP-for-everything**: LAS delegates all inference to prompt-prix via MCP, achieving centralized pool coordination. One process owns the GPU slots. Every consumer goes through it.

Two concerns reversed that position:

1. **Performance on the hot path.** MCP stdio has no authentication and serializes through a single pipe. Every specialist invocation adding a JSON-RPC round-trip through an unauthenticated transport is inappropriate for the inference hot path. Serialization overhead is small (~5ms on a 5-30s call), but the process boundary adds failure modes and debugging complexity to every LLM interaction.

2. **MCP security model.** MCP stdio transport has no caller identity, no audit trail, and no access control. Making it the sole inference gateway means any process with `docker exec` access has unrestricted access to all models. This is acceptable for occasional eval/analysis calls; it's not acceptable for the primary inference pathway that handles prompt content.

This ADR reflects the revised position: **direct import for inference (hot path), MCP for evaluation/analysis (cold path)**. The tradeoff is explicit: we gain hot-path performance and security, and we lose centralized cross-consumer pool coordination. The next section addresses that gap honestly.

### Cross-Consumer JIT-Swap Risk (Accepted)

With two independent pool instances (LAS and prompt-prix) pointing at the same LM Studio servers, cross-consumer JIT-swap protection does not exist. The specific failure mode:

1. LAS's pool thinks server 1 has Model A loaded (its `current_model` says so)
2. prompt-prix's pool dispatches Model B to server 1
3. LAS sends Model A request → LM Studio unloads B mid-stream → "Stream aborted"
4. Neither pool knows about the other's `current_model` state

JIT-swap protection only works *within* a single pool instance. Two independent pools get zero cross-consumer protection.

**We accept this risk** because:

- Simultaneous multi-model usage across consumers is operationally uncommon in our setup. LAS runs interactive workflows; prompt-prix runs batch evaluations. These are rarely concurrent.
- LM Studio server-side queuing handles concurrent same-model requests from multiple consumers without issue. The risk is specifically cross-model swaps, which require both consumers actively requesting different models on the same server at the same time.
- The alternative (centralized pool via MCP or shared process with IPC) has costs that exceed the risk: MCP security/performance concerns, or non-trivial shared-state IPC infrastructure.

**If this becomes a real problem**, the fix is not additive — it requires a shared pool process with IPC, which is a fundamental restructuring. The honest assessment is that this is a known gap we choose to live with, not something we can bolt on later.

---

## Decision

### Extract pool infrastructure to a standalone package; consume via two paths

#### 1. Extract `local-inference-pool` as a standalone package

The pool infrastructure (`ServerPool`, `ConcurrentDispatcher`, `ServerConfig`) moves to a new repository: `local-inference-pool`.

**What moves:**

| Component | Lines | Current location |
|-----------|-------|-----------------|
| `ServerPool` | ~150 | `prompt_prix/adapters/lmstudio.py` (class `_ServerPool`) |
| `ConcurrentDispatcher` | ~100 | `prompt_prix/adapters/lmstudio.py` (class `_ConcurrentDispatcher`) |
| `ServerConfig` | ~30 | `prompt_prix/config.py` (Pydantic model) |

~280 lines. Dependencies: `httpx`, `pydantic`. Zero application-level imports.

**API changes from internal to public:**
- Drop underscore prefixes: `_ServerPool` → `ServerPool`, `_ConcurrentDispatcher` → `ConcurrentDispatcher`
- `ServerConfig` stays as-is (already clean)

**Package structure:**

```
local-inference-pool/
├── pyproject.toml
├── local_inference_pool/
│   ├── __init__.py          # Public API exports
│   ├── pool.py              # ServerPool
│   ├── dispatcher.py        # ConcurrentDispatcher
│   └── config.py            # ServerConfig
└── tests/
    ├── test_pool.py          # Slot tracking, model routing, JIT-swap protection
    └── test_dispatcher.py    # Queue management, cancellation, concurrent dispatch
```

Both prompt-prix and LAS add `local-inference-pool>=0.1.0` as a declared dependency.

**Pool scope:** The pool is model-routing infrastructure, not request-handling infrastructure. It routes by `model_id` and manages server slots. It does not know about request schemas — prompt-prix uses `InferenceTask` (model_id, messages, temperature, max_tokens, timeout_seconds, tools, seed, repeat_penalty), LAS uses `StandardizedLLMRequest` (messages, model_id, output_model_class, tools, force_tool_call, image_data). The pool doesn't care. Each consumer translates its own request type into HTTP calls after the pool provides a server URL.

#### 2. LAS hot path: import pool directly

LAS adds a `PooledLMStudioAdapter` that wraps the extracted pool with the existing `BaseAdapter.invoke()` contract. The adapter must use `ConcurrentDispatcher.submit()`, not raw `ServerPool.find_and_acquire()`, to get the full benefit of:

- Queue management (waiting when all servers are busy)
- Cancellation handling (race-condition-safe cleanup of acquired servers)
- Head-of-line blocking rotation

```python
from local_inference_pool import ServerPool, ConcurrentDispatcher

class PooledLMStudioAdapter(BaseAdapter):
    """
    Shared pool adapter. One instance serves all specialists.

    Uses ConcurrentDispatcher for queue management and cancellation safety.
    All async pool operations are funneled through a dedicated event loop
    thread to maintain thread safety (see Thread Safety section).
    """
    def __init__(self, server_urls: list[str], model_config: dict):
        super().__init__(model_config)
        self._pool = ServerPool(server_urls)
        self._dispatcher = ConcurrentDispatcher(self._pool)
        self._loop_thread = self._start_event_loop_thread()

    def invoke(self, request: StandardizedLLMRequest) -> dict:
        model_id = request.model_id or self.model_name

        # Acquire server slot through dispatcher (handles queue, wait, cancellation)
        # submit() returns a server URL, not a completed response
        future = asyncio.run_coroutine_threadsafe(
            self._dispatcher.submit(model_id),
            self._loop
        )
        server_url = future.result(timeout=request.timeout or 300)

        # Make HTTP call to acquired server
        try:
            return self._invoke_on_server(server_url, request)
        finally:
            # Release slot — must happen even on error
            self._pool.release_server(server_url)
```

**Thread safety:** `ServerPool.find_and_acquire()` is synchronous (intentionally — "strictly synchronous is_busy state management to prevent race conditions" per its docstring). It mutates `ServerConfig.active_requests` and `current_model` directly. But `ConcurrentDispatcher.submit()` is async and manages the queue/wait loop. LAS's sync `invoke()` will be called from multiple threads (multiple specialists running concurrently in the graph).

The bridge strategy: a dedicated `asyncio` event loop running in its own thread. All pool and dispatcher operations are submitted to this loop via `run_coroutine_threadsafe()`. This ensures:
- `ServerPool` state mutations happen in one thread (the event loop thread) — no locking needed
- `ConcurrentDispatcher` queue/wait operates in its natural async context
- LAS specialist threads block on `future.result()` — simple, predictable sync behavior

This is non-trivial bridge code (~40-50 lines for loop lifecycle management) and must be tested with concurrent specialist invocations.

**LAS-specific concerns preserved:**
- `_build_tool_call_schema()` (JSON schema enforcement for structured output) stays in `PooledLMStudioAdapter`
- `_robustly_parse_json_from_text()` stays in LAS's response parsing

#### 3. LAS cold path: prompt-prix via MCP

LAS calls prompt-prix's MCP tools for evaluation and analysis:

| Tool | Use case | Timeout |
|------|----------|---------|
| `list_models` | Model discovery at startup | 30s |
| `judge` | Evaluate specialist output quality | 600s |
| `react_step` | ReAct loop evaluation | 600s |
| `calculate_drift` | Semantic drift detection | 10s |
| `analyze_variants` | Prompt optimization | 10s |
| `analyze_trajectory` | Detect circular reasoning | 10s |

This path uses the existing `ExternalMcpClient` infrastructure (already wired in docker-compose.yml and config.yaml). No new adapter needed — these are MCP tool calls, not inference requests.

---

## What Changes Where

### prompt-prix

| File | Change |
|------|--------|
| `pyproject.toml` | Add `local-inference-pool>=0.1.0` dependency |
| `prompt_prix/adapters/lmstudio.py` | Replace internal `_ServerPool`/`_ConcurrentDispatcher` with imports from `local_inference_pool` |
| `prompt_prix/config.py` | Remove `ServerConfig` definition, import from `local_inference_pool` |

### LAS

| File | Change |
|------|--------|
| `pyproject.toml` | Add `local-inference-pool>=0.1.0` dependency |
| `app/src/llm/pooled_adapter.py` | **NEW**: `PooledLMStudioAdapter` with event loop bridge (~100 lines) |
| `app/src/llm/factory.py` | Register `lmstudio_pool` type in `ADAPTER_REGISTRY` |
| `app/src/llm/adapter.py` | Add `model_id: Optional[str] = None` to `StandardizedLLMRequest` |
| `app/src/workflow/graph_builder.py` | Simplify adapter wiring to shared pool reference |
| `config.yaml` | `server_urls` list replaces per-specialist `base_url` (see Config Migration) |

### Config Migration

Adding `model_id` to `StandardizedLLMRequest` is one line. The ripple is in who sets it and how:

**Current state:** Each specialist has its own adapter instance with a hardwired `model_name`. The specialist never thinks about model selection — it's decided at construction time in GraphBuilder.

**New state:** One shared adapter, model selection per request. Three options for how specialists get their model:

| Approach | Mechanism | Tradeoff |
|----------|-----------|----------|
| **Graph builder injects** | `specialist.default_model = "qwen3-8b"` set during `_attach_llm_adapter()` | Minimal specialist changes, familiar pattern |
| **Config-driven** | `config.yaml` maps specialist → model, adapter reads at call time | More flexible, but config schema changes |
| **Dynamic** | Specialist chooses model based on task requirements | Most flexible, most complex |

Phase 1 uses "graph builder injects" — the smallest change. Each specialist gets a `default_model` attribute set during graph construction. `PooledLMStudioAdapter.invoke()` resolves `request.model_id or specialist.default_model or pool_default`.

What happens when a specialist's preferred model isn't available on any server: `ConcurrentDispatcher.submit()` waits in its queue until a server with that model becomes available, or times out. This is the existing behavior for within-pool model availability — no new handling needed.

### Unchanged

| Concern | Why |
|---------|-----|
| All specialists | `invoke(StandardizedLLMRequest)` contract preserved |
| MCP infrastructure | External MCP is independent of adapter layer |
| Graph structure | Nodes, edges, subgraphs unchanged |
| Prompt content | System prompts stay the same, assembled differently |
| Response parsing | `_build_tool_call_schema()`, `_robustly_parse_json_from_text()` preserved |

---

## Consequences

### Positive

- **Structural boundary enforcement** — pool abstraction is protected by package versioning, not convention
- **Multi-server load balancing** — requests route to least-loaded server with the required model
- **JIT-swap protection (within consumer)** — pool refuses to dispatch a different model to a server with active requests from that consumer
- **GraphBuilder simplification** — ~150 lines of per-specialist adapter wiring collapses
- **Hot/cold path separation** — inference stays direct (performance/security), evaluation goes through MCP (simplicity)
- **Model-at-call-time** — `StandardizedLLMRequest.model_id` enables dynamic model selection
- **Future consumer readiness** — distill-mcp or any new project adds the dependency, gets pool for free
- **Change management discipline** — breaking pool API changes require version bump + opt-in

### Negative

- **Third repo** — adds release management, versioning, cross-repo dependency coordination
- **Coordination tax** — every pool change requires version bump → release → dependency update in 2+ repos → CI verification. For code actively being iterated on (e.g., `current_model` tracking was added recently), this friction is real. The boundary enforcement value exceeds the coordination cost, but the cost is nonzero.
- **Event loop bridge complexity** — wrapping async dispatcher in sync `invoke()` requires a dedicated event loop thread with lifecycle management (~40-50 lines of non-trivial bridge code)
- **No cross-consumer JIT-swap protection** — LAS and prompt-prix pools don't coordinate model state across consumers (see Cross-Consumer JIT-Swap Risk section)

### Risks

- **Thread safety in LAS** — `ServerPool` was designed for single-threaded async; LAS's sync bridge must funnel all operations through the event loop thread. If any pool method is called directly from a specialist thread, state corruption results. Mitigation: `PooledLMStudioAdapter` encapsulates all pool access — specialists never touch pool directly, and the adapter enforces the event-loop-thread invariant.
- **Version skew** — LAS and prompt-prix could pin different versions. Mitigation: semver discipline, CI that tests against latest.
- **Config migration complexity** — existing `base_url` per-specialist configs need migration to `server_urls` + `default_model`. Mitigation: run both adapter types (`lmstudio` and `lmstudio_pool`) in parallel during migration, switch specialists incrementally.

---

## Versioning Strategy

**Who drives changes:** prompt-prix is the primary consumer and the team most familiar with pool internals. Pool changes originate as PRs against `local-inference-pool`, reviewed by the same team.

**Breaking changes:** The pool's public API is small (`ServerPool.find_and_acquire()`, `ServerPool.release_server()`, `ConcurrentDispatcher.submit()`, `ServerConfig` fields). Breaking changes to these require a major version bump. All consumers must explicitly opt in by updating their pinned version.

**Non-breaking changes (patch/minor):** Internal optimizations, new optional `ServerConfig` fields, bug fixes. Consumers get these automatically if they pin `>=0.1.0`.

**Practical cadence:** During active development, both repos pin to `>=0.x.0` (minor range). Once the pool stabilizes post-extraction, pin to `>=0.x.0,<1.0.0` for safety. After v1.0.0, standard semver applies.

---

## Why This Subsumes ADR-067

ADR-067 and ADR-068 share the same goals:

| Goal | ADR-067 mechanism | ADR-068 mechanism |
|------|-------------------|-------------------|
| Multi-server support | Port pool into LAS | Import pool from extracted package |
| Eliminate N adapters | Shared `PooledLMStudioAdapter` | Same, but pool is imported, not ported |
| Model-at-call-time | `StandardizedLLMRequest.model_id` | Same |
| GraphBuilder simplification | Collapse to shared pool | Same |

The difference is **where the pool lives**:
- ADR-067: Copied into `app/src/llm/pool.py` (code duplication, convention-enforced boundaries)
- ADR-068: Imported from `local-inference-pool` (single source of truth, structurally-enforced boundaries)

ADR-068 additionally:
- Introduces the hot/cold path separation (direct import for inference, MCP for evaluation)
- Explicitly addresses thread safety bridge requirements
- Honestly treats the cross-consumer JIT-swap gap as an accepted risk rather than a solvable problem
- Scopes the config migration ripple (specialist model binding)
- Defines a versioning strategy for the extracted package

---

## References

- **prompt-prix adapter**: `prompt_prix/adapters/lmstudio.py` — current home of `_ServerPool`, `_ConcurrentDispatcher`
- **prompt-prix ADR-006**: Adapter Owns Pool and Dispatcher (encapsulation principle)
- **ADR-CORE-054**: Dispatcher Sync-Async Boundary (bridge pattern precedent)
- **ADR-CORE-066**: Sleeptime Autonomous Orchestration (consumer of model-at-call-time)
- **ADR-MCP-004**: LLM-Backed MCP Services (model-at-call-time pattern)
- **ADR-CORE-067**: Adapter Convergence — Shared Pool Architecture (subsumed by this ADR)

---

## Implementation Notes (Feb 2026)

### Extraction Completed

`local-inference-pool` v0.1.0 extracted as standalone package. Both LAS and prompt-prix consume it as a declared dependency. The package structure matches the proposal.

### Validation Results

| Check | Result |
|-------|--------|
| Pool init | Pass |
| Manifest refresh | Pass (59 models discovered across servers) |
| Pre-flight server pings | Pass |
| Triage + Router execution via pool | Pass |
| LAS unit tests | 790 pass |

### Bugs Discovered During Integration

Three bugs surfaced during smoke testing that the proposal didn't anticipate:

1. **`config_loader.py:182` — server name resolution**: The `lmstudio_pool` adapter type wasn't included in the type check for server→base_url resolution. Config loader resolved `lmstudio` server names but silently passed `lmstudio_pool` entries through unresolved. Fix: added `lmstudio_pool` to the resolution type check.

2. **`pooled_adapter.py:92` — `/v1` path stripping**: The pool strips `/v1` from server URLs for internal routing (it manages base URLs). But the OpenAI SDK client requires the `/v1` suffix. The adapter must re-add `/v1` when constructing the SDK client URL after receiving a server slot from the pool.

3. **`lmstudio_adapter.py:423` — null choices guard**: LM Studio returns `choices=null` (not empty list, not missing — literal null) when a request hits the wrong endpoint. The response parser assumed `choices` was always iterable. Fix: null guard before iteration.

### Deviations from Proposal

- **Config migration**: Phase 1 "graph builder injects" approach implemented as proposed. Per-specialist `base_url` configs coexist with the shared `server_urls` pool — both adapter types (`lmstudio` and `lmstudio_pool`) run in parallel during migration, as the proposal recommended.
- **Event loop bridge**: Implemented as proposed (~40-50 lines). Thread safety validated with concurrent specialist invocations through the graph.

### Accepted Risk Status

The cross-consumer JIT-swap risk (two independent pools, LAS + prompt-prix) remains accepted. No cross-model swap incidents observed in practice — usage pattern confirms the proposal's assessment that simultaneous multi-model usage across consumers is operationally uncommon.
