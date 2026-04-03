# Proposal: Two-Headed Architecture — Chat Head + Observability Head

## For: Claude Code resuming from compact context on the OpenAI-First Migration Plan

## What this document is

The current plan (OpenAI-First API Migration) threads LAS observability data through `las_metadata` fields on OpenAI `ChatCompletionChunk` objects and treats the migration as a single linear sequence of phases. This proposal revises the plan based on a structural analysis of V.E.G.A.S. Terminal's app.js and architectural discussion about the actual consumer needs. The result is three independent workstreams, a cleaner separation of concerns, and a careful deprecation path that ensures LAS is always promptable at every step.

## The core insight

V.E.G.A.S. Terminal is two products sharing a codebase:

1. **A chat client** — the command bar, file upload, request construction (~80 lines of concern #5 in app.js). This is the least interesting part of V.E.G.A.S. and the part AnythingLLM replaces.

2. **An observability dashboard** — thought stream, routing log, neural grid, snapshot inspector, tool chain viewer, mission report paging with context selection. This is a bespoke LangSmith equivalent that already works. It talks to `/v1/graph/stream/events`, `/v1/progress/{run_id}`, `/v1/traces/{run_id}`, `/v1/graph/topology`. None of these endpoints have OpenAI equivalents, and they don't need one.

These two products have different consumers, different protocols, and different lifecycles. The current plan entangles them by trying to carry observability data on OpenAI chunks via `las_metadata`. This proposal separates them.

## What changes from the current plan

### Drop `las_metadata` from the OpenAI stream

The current plan defines `las_metadata` fields on `ChatCompletionChunk` for specialist_start, thought, routing, mcp, artifact_update. These exist solely to feed V.E.G.A.S. observability panels through the OpenAI stream.

Remove this. The OpenAI stream produces spec-compliant chunks with no vendor extensions. Standard clients work without modification — that's the entire point of adopting the protocol. The observability data already has its own delivery path and doesn't need a new one.

### Leave observability untouched

The observability surface is not capable of mapping to a standard protocol, and it doesn't need to. The existing endpoints and event stream work. The rendering code (thought stream, snapshot inspector, mission report, topology — concerns #2, #3, #4, #6 in the app.js analysis) is wire-format-agnostic in practice. It consumes normalized data shapes, not raw SSE.

No new `ObservabilityEvent` schema. No new `/v1/observe/{run_id}` endpoint. No `ObservePollingAdapter`. The observability product gets lifted out of the migration scope entirely.

### EventAdapter extraction becomes optional

The current plan's Phase 0 (extract EventAdapter from app.js) was designed to create a seam where a second adapter could plug in for OpenAI chunks. Since V.E.G.A.S. is no longer migrating to consume OpenAI chunks — it stays on its existing event stream — the adapter refactor is no longer on the critical path. It's still good engineering for code quality in a 2000-line JS file, but it doesn't block anything and can happen whenever.

### V.E.G.A.S. UI refactor is its own project

Removing the chat input and reclaiming screen real estate for observability panels is a client-side-only change with no API dependencies. It doesn't need the OpenAI endpoint to exist first. It doesn't change any server code. It's a separate atomic project.

## Three independent workstreams

These have no dependencies on each other (except Workstream 3 depends on Workstream 1) and can proceed in any order or in parallel.

### Workstream 1: OpenAI Chat Endpoint (server-side only)

**Goal:** Any OpenAI client can connect to LAS and get responses.

**Scope:**
- `openai_schema.py` — standard ChatCompletionRequest/Response/Chunk with no vendor extensions
- `openai_request_adapter.py` — translates OpenAI message format to WorkflowRunner kwargs
- `openai_translator.py` — consumes WorkflowRunner.run_streaming() events, produces ChatCompletionChunk objects with content only
- `api.py` modifications — `POST /v1/chat/completions` (sync + streaming), `GET /v1/models` (routing profiles as model list)

**Does not include:** Any `las_metadata` on chunks. Any client-side changes. Any V.E.G.A.S. modifications.

**Pattern to follow:** `ag_ui_schema.py` (35 lines, focused Pydantic models), `translator.py` (214 lines, event consumption + formatting).

**The `model` field:** Routing profile selector. `las-default`, `las-simple`, `las-research`, etc. ADR-UI-002's update about Generic OpenAI provider confirms this — model name is a freeform string, no model enumeration required. Actual LLM model info is observability data that shows up in state snapshots, not in the chat response.

**Content delivery:** `final_user_response.md` arrives as a single burst in `delta.content` after specialist work completes. During execution, the chat stream is silent. This is fine — standard clients wait for the response. Clients that want to see what's happening during the silence use the observability dashboard.

**Interrupt/clarification for standard clients:** Degrade gracefully. When LAS hits an interrupt, return `finish_reason: "stop"` with the clarification questions as regular content ("I need more information before proceeding: [questions]"). The structured interrupt path (`finish_reason: "requires_action"` + `/v1/graph/resume`) remains available for LAS-aware clients, but a vanilla openai-python user gets a usable experience without knowing about it. This is the pragmatic first pass — full multi-turn interrupt/resume through the messages array (correlating by conversation_id) is the right long-term answer but not needed for initial deployment.

**Verification:**
- `pytest app/tests/unit/test_openai_*.py -v`
- `curl -X POST localhost:8000/v1/chat/completions -d '{"model":"las-default","messages":[{"role":"user","content":"hello"}]}'`
- Same with `"stream": true`, verify SSE format
- AnythingLLM Generic OpenAI provider connects and gets responses

### Workstream 2: V.E.G.A.S. Observability UI Refactor (client-side only)

**Goal:** Reclaim the chat input real estate for observability panels. V.E.G.A.S. becomes a dedicated observability dashboard.

**Scope:**
- Remove or hide the command bar panel (promptInput, executeBtn, cancelBtn, file upload)
- Remove request construction code (concern #5, ~80 lines in app.js)
- Expand observability panels into the reclaimed space
- All existing observability functionality stays exactly as-is: SSE consumption from `/v1/graph/stream/events`, progress polling, topology visualization, thought stream, snapshot inspector, mission report

**Does not include:** Any server changes. Any API changes. Any new endpoints. Any new adapters or schemas.

**The SSE consumption stays on `/v1/graph/stream/events`.** The AgUiTranslator already produces the events. The rendering code already consumes them. There is no reason to change this. The observability surface is not migrating to a different protocol.

**Note:** This workstream is explicitly deferred until the chat deprecation transition (below) reaches the appropriate step. V.E.G.A.S. keeps its chat input until AnythingLLM is validated.

### Workstream 3: Gradio Migration (small, depends on Workstream 1)

**Goal:** Gradio UI uses the OpenAI endpoint instead of the bespoke one.

**Scope:**
- Modify `app/src/ui/api_client.py` (107 lines) to call `/v1/chat/completions` instead of `/v1/graph/stream`
- Parse ChatCompletionChunk instead of custom JSON
- Minimal changes to Gradio UI files that consume api_client's generator

**After completion:** `/v1/graph/stream` and `_stream_formatter()` have no consumers. Remove them.

## V.E.G.A.S. chat deprecation transition

This is the careful, phased process for migrating from V.E.G.A.S. as the chat interface to an external OpenAI client (AnythingLLM or equivalent). The constraint is that LAS must be promptable at every step — there is never a moment where the chat input is gone but the replacement isn't ready.

### Step 1: Build the OpenAI endpoint. Change nothing in V.E.G.A.S.

This is Workstream 1. Pure server-side additive work. When done, `curl` works against `/v1/chat/completions`. V.E.G.A.S. is untouched, still talks to `/v1/graph/stream/events`, still has its chat input. LAS is promptable exactly as before.

### Step 2: Validate AnythingLLM integration empirically.

Point AnythingLLM's Generic OpenAI provider at LAS. Test:
- Does streaming work through AnythingLLM's proxy without corruption?
- Does model selection (`las-default`, `las-research`, etc.) work with the freeform model name field?
- What happens when RAG context is prepended to the messages array? Does it conflict with LAS's own context handling?
- Does the interrupt/clarification degradation (questions returned as regular content) produce a usable experience?
- What does latency feel like for real analysis tasks through the AnythingLLM layer?

V.E.G.A.S. is still untouched. There are now two ways to prompt LAS — AnythingLLM and V.E.G.A.S. — and they can be compared side by side. This is the empirical research ADR-UI-002 identifies as not yet done.

### Step 3: Live with both for a while.

This is not a phase to rush through. Use AnythingLLM for actual analysis work. Use V.E.G.A.S. for observability. Evaluate whether the workspace model (research workspace → `las-research`, project workspace → `las-default`, passthrough workspace → `las-passthrough`) maps to how you actually work. Discover the friction points that only show up with real use.

### Step 4: V.E.G.A.S. chat input becomes optional.

Add a config toggle or UI control — a "headless mode" flag — that hides the command bar and reclaims the real estate for observability panels. The chat input code stays in the file, just hidden. If AnythingLLM has a bad day, flip the toggle back and you're exactly where you started. This is Workstream 2 in its initial, reversible form.

### Step 5: Remove V.E.G.A.S. chat input.

Only after you're confident the external chat client is the permanent path. Remove concern #5 (request construction, ~80 lines), the command bar HTML, the file upload logic. This is Workstream 2 in its final, irreversible form. By this point you've been running the new setup long enough to know it works.

**Key property of this sequence:** Steps 1-3 involve zero changes to V.E.G.A.S. Step 4 is reversible. The only irreversible step is 5, and it's gated on lived experience with the replacement.

## What this answers

**Q1 (metadata transport):** Metadata doesn't travel in OpenAI responses. It has its own existing channel that doesn't change. Standard clients get clean responses. The observability dashboard talks to the same endpoints it always has.

**Q2 (V.E.G.A.S. migration target):** V.E.G.A.S. doesn't migrate to OpenAI chunks. It stays on `/v1/graph/stream/events` for observability. Its chat input gets removed (eventually, carefully) and replaced by an external OpenAI client.

**Q3 (model field):** Routing profile selector. `las-default`, `las-simple`, `las-research`. Confirmed compatible with AnythingLLM's Generic OpenAI provider which accepts freeform model name strings.

**Q4 (streaming silence):** Not a problem. The chat stream is silent during specialist execution. Clients that want progress visibility use the observability dashboard. Clients that don't care just wait. The two concerns are served by two different surfaces.

## Risk assessment

| Item | Risk | Mitigation |
|------|------|------------|
| Workstream 1 (OpenAI endpoint) | Low | Additive server-side code, existing patterns to follow |
| Workstream 2 (V.E.G.A.S. UI refactor) | Low | Client-side only, reversible via toggle |
| Workstream 3 (Gradio migration) | Low | 107-line client, old endpoint stays alive until verified |
| AnythingLLM streaming fidelity | Unknown | Empirical testing in Step 2, V.E.G.A.S. remains available throughout |
| AnythingLLM RAG interaction with LAS context | Unknown | Empirical testing in Step 2 |
| Interrupt/clarification UX in standard clients | Medium | Graceful degradation (Option 3) for first pass, revisit after lived experience |
| Transition period (running both interfaces) | None | Both coexist indefinitely, no deadline pressure |

## Critical files

| File | Role | Workstream |
|------|------|------------|
| `app/src/api.py` (709 lines) | Add OpenAI endpoints | 1 |
| `app/src/interface/ag_ui_schema.py` (35 lines) | Pattern for new schema | 1 |
| `app/src/interface/translator.py` (214 lines) | Pattern + reusable reducer logic | 1 |
| `app/src/workflow/runner.py` (391 lines) | Raw stream contract — must not change | — |
| `app/web-ui/public/app.js` (2000+ lines) | Remove chat input, expand observability | 2 |
| `app/src/ui/api_client.py` (107 lines) | Gradio consumer to migrate | 3 |

## Summary of deltas from current plan

| Current plan | This proposal |
|---|---|
| `las_metadata` on ChatCompletionChunk | No vendor extensions on chunks |
| Single linear phase sequence | Three independent workstreams |
| Observability migrates to new delivery mechanism | Observability lifted out untouched |
| EventAdapter extraction is Phase 0 blocker | EventAdapter extraction is optional code quality improvement |
| V.E.G.A.S. consumes OpenAI chunks via new adapter | V.E.G.A.S. stays on existing event stream |
| V.E.G.A.S. chat input replaced in one phase | Five-step deprecation: build → validate → coexist → toggle → remove |
| Phase 5 (V.E.G.A.S. JS migration) is highest risk item | V.E.G.A.S. JS migration doesn't happen — rendering code untouched |

## Install script (separate workstream, unchanged from current plan)

Modify `scripts/setup.sh` (410 lines):
- Rename `LMSTUDIO_BASE_URL` → `LOCAL_INFERENCE_BASE_URL`
- Generated `user_settings.yaml`: use `type: "local"` not `"lmstudio"`
- Add sibling repo detection for semantic-chunker, prompt-prix, webfetch-mcp
- Add MCP profile selection step
- Detect Docker GID automatically (`stat -c '%g' /var/run/docker.sock`)

---

## Status: COMPLETE

**Date:** 2026-03-09
**Completed:** 2026-04-03

### WS1 (OpenAI Chat Endpoint): COMPLETE

All server-side code implemented, 47 new unit tests passing. Merged to main.

- `app/src/interface/openai_schema.py`
- `app/src/interface/openai_request_adapter.py`
- `app/src/interface/openai_response_formatter.py`
- `app/src/interface/openai_translator.py`
- `app/tests/unit/test_openai_*.py` (4 test files)
- `app/src/api.py` — `/v1/chat/completions`, `/v1/models` endpoints

### WS2 (Observability Extraction): COMPLETE

The observability layer is now an independent module that can be developed, tested, and toggled separately from both the chat UI and the execution layer. V.E.G.A.S. chat deprecation (Steps 4-5) is structurally trivial — removing a `<script>` tag.

**Server-side extraction:**

| New File | Lines | Purpose |
|----------|-------|---------|
| `app/src/observability/event_bus.py` | 52 | `EventBus` — pub/sub contract between execution and observation |
| `app/src/observability/active_runs.py` | 46 | `ActiveRunRegistry` — shared state for run discovery |
| `app/src/observability/router.py` | 330 | FastAPI `APIRouter` — all 6 observability endpoints |
| `app/src/observability/__init__.py` | 25 | Module surface: event_bus, active_runs, router, init |

`api.py` reduced from 948 → 641 lines. Observability router mounted via `app.include_router()`. Dependencies injected via `init_observability()` in FastAPI lifespan.

**Client-side extraction:**

The 2146-line `app.js` monolith split into three files loaded in order:

| File | Lines | Purpose |
|------|-------|---------|
| `app.js` | 257 | Shared state, DOM refs, utilities, theme, tabs |
| `observability.js` | 1423 | Rendering, event handling, polling, headless mode |
| `chat.js` | 363 | Workflow execution, file upload, abort, clarification |

**Key property:** Removing the `<script src="chat.js">` tag from `index.html` turns V.E.G.A.S. into a pure observability dashboard. No server changes needed. This is ADR-UI-003 WS2 Step 4 (the toggle) — now it's a one-line HTML change instead of extracting code from a monolith.

**Dependency direction:** Execution → Observability (push events). The observability module defines the contract surface (`EventBus`, `ActiveRunRegistry`); chat heads call into it. Observability never imports from chat.

### WS3 (Gradio Migration): DEFERRED

Depends on WS1 being exercised end-to-end. 107-line client change. Not blocked by anything architectural — just not prioritized.

### Architectural outcome

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI (api.py)                       │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────────────────────┐ │
│  │   Chat Head      │  │   Observability Module           │ │
│  │                  │  │                                  │ │
│  │  /v1/graph/*     │─→│  event_bus (push)                │ │
│  │  /v1/chat/*      │─→│  active_runs (register)          │ │
│  │  /v1/models      │  │                                  │ │
│  │  /v1/system/*    │  │  /v1/runs/active                 │ │
│  │                  │  │  /v1/runs/{id}/events             │ │
│  └──────────────────┘  │  /v1/progress/{id}               │ │
│                        │  /v1/traces/{id}                  │ │
│                        │  /v1/graph/topology               │ │
│                        │  /v1/archives/{file}              │ │
│                        └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         ↓                              ↓
  ┌──────────────┐           ┌─────────────────────┐
  │  AnythingLLM │           │  V.E.G.A.S.         │
  │  (or curl,   │           │  observability.js    │
  │   OpenAI SDK)│           │  + optional chat.js  │
  └──────────────┘           └─────────────────────┘
```
