# LAS Architecture Reference

**Updated:** 2026-02-22

---

## 1. Identity

**LAS** (langgraph-agentic-scaffold) is a Python orchestration framework for multi-model agentic workflows with structural safety constraints.

**Core thesis:** LLMs are unreliable and potentially manipulative. The framework enforces safety through structure, not trust. Every specialist executes inside a safety wrapper. No specialist can unilaterally terminate, corrupt state, or bypass the control plane.

**Architectural metaphor:** LAS applies computing primitives to LLM orchestration:

| Computing Concept | LAS Equivalent | Purpose |
|-------------------|----------------|---------|
| **CPU / Scheduler** | Router | Turn-by-turn routing decisions |
| **Stack** | Context Window | Ephemeral per-invocation working memory |
| **Heap** | Artifacts | Persistent, cross-specialist shared state |
| **System Calls** | MCP | Synchronous service invocation bypassing Router |
| **Process Fork** | fork() | Context-isolated subtask with own lifecycle |
| **Signals** | signals field | Asynchronous inter-node communication (ADR-077) |

**Explicit MoE:** LAS specialist routing is a visible, auditable version of what happens implicitly inside a transformer's Mixture-of-Experts layers. The Router is the gating function. Specialists are the experts. The routing decision is observable, loggable, and adjustable — unlike implicit MoE where expert selection happens in hidden dimensions.

---

## 2. Ecosystem

LAS is the composition layer for an ecosystem of independently-developed AI services. Each sibling repo is a self-contained capability module with its own UI, tests, and development cycle. LAS orchestrates them through MCP.

| Service | Repo | Role in Ecosystem |
|---------|------|-------------------|
| **prompt-prix** | `prompt-prix/` | LLM interface + eval platform. LAS never calls LLMs directly — prompt-prix owns the model boundary via `react_step` MCP. Also provides battery evaluation, model tournament, and a Gradio eval UI. |
| **semantic-chunker** | `semantic-chunker/` | Embedding infrastructure. embeddinggemma-300m (768-d) default, NV-Embed-v2 (4096-d). Provides `calculate_drift`, `classify_document`, `analyze_variants` — the measurement tools for prompt geometry research. |
| **surf-mcp** | `surf-mcp/` | Browser automation with Fara visual grounding. Perception layer for web interaction. |
| **local-inference-pool** | `local-inference-pool/` | Multi-GPU compute substrate. Routes model requests across rtx8000 + rtx3090 with JIT-swap guard and least-loaded balancing. Consumed via `PooledLMStudioAdapter`. |
| **it-tools-mcp** | `it-tools-mcp/` | 119 IT utility tools (format_json, convert_json_to_csv, etc.). Standard library wired to TextAnalysisSpecialist. |

**Repo boundaries are context firewalls.** Separate repos prevent AI assistants from accidentally growing or damaging code that exceeds their context window. Each repo is independently comprehensible.

---

## 3. Architectural Primitives

### 3.1 GraphState
Central state object passed between all nodes. Uses `Annotated` types for merge behavior.

```python
messages: Annotated[list, operator.add]      # Append-only conversation
artifacts: Annotated[dict, operator.ior]     # Dict merge for outputs
scratchpad: dict                             # Ephemeral working memory
signals: dict                                # Inter-node communication (replace reducer, ADR-077)
routing_history: list                        # Execution path tracking
turn_count: int                              # Recursion control
```

**Three-field architecture:**
- **Scratchpad** — ephemeral, cleared after routing. Specialist-to-Facilitator communication.
- **Artifacts** — persistent, dict-merge. Cross-specialist shared state.
- **Signals** — replace reducer, consumed by SignalProcessor. Routing-level communication (max_iterations_exceeded, stagnation_detected).

### 3.2 BaseSpecialist
All specialists inherit from `BaseSpecialist`. Contract:
- `_execute_logic(state) -> dict` — Core logic, returns state updates
- `_perform_pre_flight_checks() -> bool` — Validation before execution
- `register_mcp_services(registry)` — Optional MCP service exposure

Specialists never mutate state directly. They return dicts that SafeExecutor merges.

### 3.3 NodeExecutor (SafeExecutor)
Wraps all specialist execution:
- Invariant checking (pre/post execution)
- Error isolation and circuit breaker triggering
- Observability hooks (state_timeline, LangSmith tracing)

**Exception:** Router bypasses SafeExecutor to preserve `turn_count` handling (only Router can increment it). Router includes its own observability hooks directly.

### 3.4 MCP (Model Context Protocol)
Synchronous service invocation between specialists. Two types:
- **Internal MCP:** Python functions registered in `McpRegistry`
- **External MCP:** Containerized services via stdio JSON-RPC (filesystem, terminal, semantic-chunker, prompt-prix, surf-mcp, it-tools)

MCP is for deterministic service calls. The dossier pattern is for LLM-driven handoffs through the graph.

---

## 4. Routing Architecture

### 4.1 Hub-and-Spoke
Router is the central hub. All specialists return to Router after execution.

```
User → Triage → SA → Facilitator → Router → Specialist → SignalProcessor → EI → ... → End
```

### 4.2 Entry Pipeline (Context Engineering)
Every request flows through the entry pipeline before reaching Router:

```
User Request
    ↓
TriageArchitect ──→ ACCEPT/REJECT gate (thin classifier, not planner)
    ↓ [PASS]
SystemsArchitect ──→ Produces task_plan (write-once master intent + acceptance_criteria)
    ↓
Facilitator ──→ Assembles gathered_context (always runs, sole context writer)
    ↓
Router ──→ Routes with gathered_context available
```

**Facilitator pattern (ISO-9000 Context Management):** Specialists don't fetch context — they receive it. Facilitator is the single point of context assembly. Context-related fixes belong in Facilitator, not specialists.

### 4.3 Signal Processor (ADR-077)
After specialist execution, SignalProcessor reads the `signals` field to classify interrupt type:
- **Normal** → Exit Interview for completion check
- **BENIGN** (max_iterations_exceeded) → EI with `routing_context: "benign_continuation"`
- **PATHOLOGICAL** (stagnation_detected) → Interrupt Evaluator → EI → Router fallback chain

### 4.4 Routing Modes
Three routing modes:
1. **Declarative:** Explicit `next_specialist` in scratchpad
2. **Procedural:** Decider functions in `GraphOrchestrator`
3. **Probabilistic:** Router LLM chooses based on capability descriptions

### 4.5 Subgraphs
Encapsulated multi-specialist workflows that appear as single nodes:
- **Tiered Chat:** Alpha || Bravo → Synthesizer (multi-model adversarial validation)
- **Context Engineering:** Triage → SA → Facilitator → Router
- **Generate-Critique-Refine:** WebBuilder → Critic loop (max 3)

---

## 5. Core Execution Patterns

### 5.1 ReAct Tool Use (react_step MCP)
```
Specialist with tools
    ↓
┌──────────────────────────────────────────┐
│ Loop until DONE (via call_react_step):   │
│   1. call_react_step() → prompt-prix MCP │
│   2. prompt-prix makes LLM call          │
│   3. Specialist dispatches tool calls    │
│   4. Append observations to trace        │
│   5. Publish progress for live UI        │
│   6. Check max_iterations / stagnation   │
└──────────────────────────────────────────┘
    ↓
Specialist writes artifacts + signals
```

**Consumers:** ProjectDirector (filesystem/terminal/fork), TextAnalysisSpecialist (semantic-chunker/it-tools), ExitInterview (filesystem/artifacts).

**Shared helper:** `app/src/mcp/react_step.py` provides `ToolDef` + `call_react_step` + `build_tool_schemas` + `dispatch_external_tool`. Any specialist becomes ReAct-capable by defining a tool routing table and looping on `call_react_step()`.

### 5.2 fork() — Context-Isolated Subtasks (ADR-045)
```
Parent specialist (e.g., ProjectDirector)
    ↓
dispatch_fork(prompt, context, expected_artifacts)
    ↓
Child graph.invoke() — full LAS pipeline in isolated context
    ↓
extract_fork_result() → concise result returned to parent
```

**fork() = context garbage collection.** Child does work in its own context window, returns a concise result. Parent grows by result size, not work size.

Features:
- **Conditioning frame** — prepended anti-fabrication prompt (#205). Reframes reward landscape so honest failure reports and task completion are equally valued.
- **Expected artifacts** — structured result extraction via `write_artifact` keys (#206)
- **Child archiving** — children write full archives with `parent_run_id` for bidirectional navigation
- **Fork metadata** — child_run_id + child_routing_history captured for live UI breadcrumbs and post-hoc inspection

### 5.3 Tiered Chat (CORE-CHAT-002)
```
Router
    ↓
┌───────┬───────┐
│ Alpha │ Bravo │  (parallel, different models/providers)
└───┬───┴───┬───┘
    ↓       ↓
TieredSynthesizer ──→ Combines perspectives
```

Multi-model adversarial validation. Different providers reduce correlated errors.

---

## 6. Safety Mechanisms

### 6.1 Invariant Monitor
Checks system health before each specialist execution:
- State structure validity
- Max turn count (recursion limit)
- Loop detection (A→B→A→B pattern)

Violations trigger circuit breaker → stabilization action (HALT or ROUTE_TO_ERROR).

### 6.2 Fail-Fast Validation
- **Startup:** Critical specialists must load or app fails
- **Connectivity:** `verify_connectivity.py` validates LLM provider reachability before app starts
- **Routing:** Unknown destinations raise `WorkflowError`

### 6.3 Four-Stage Termination
No specialist can unilaterally terminate:
1. Specialist produces artifacts
2. SignalProcessor classifies interrupt type (ADR-077)
3. Exit Interview evaluates completion with tool-based verification
4. EndSpecialist synthesizes final response
5. ArchiverSpecialist records atomic archive package

### 6.4 Structural Defenses

| Defense | Against | Mechanism |
|---------|---------|-----------|
| SafeExecutor wrapper | Arbitrary state mutation | All specialist execution sandboxed |
| Context curation at boundaries | Whispering Gallery Effect (context accumulation) | Facilitator rebuilds context fresh each invocation |
| Multi-model progenitors | Correlated LLM errors | Different providers for Alpha vs Bravo |
| Conditioning frame on fork | Model fabrication (#205) | Anti-fabrication prompt reframes reward landscape |
| Stagnation detection | Infinite tool loops | Cycle detection on tool call signatures |

---

## 7. Observability

### 7.1 Live Observability (V.E.G.A.S. Terminal)

The web UI provides real-time workflow visualization. See [WEB_UI.md](WEB_UI.md) for full architecture.

| Feature | Mechanism |
|---------|-----------|
| **Thought Stream** | Semantic entries (ROUTE, MCP, FORK, THINK, ARTIFACT, ERROR) streamed via SSE |
| **Intra-node progress** | PD publishes to progress_store; UI polls `/v1/progress/{run_id}` every 2.5s |
| **Fork breadcrumbs** | Live routing path + child_run_id in Thought Stream; CHILD INVOCATION panel in Inspector |
| **Inspector** | Prompt Inspector (system/assembled prompts), Tool Chain viewer (react_trace), Scratchpad viewer |
| **Neural Grid** | Specialist node visualization with active highlighting |

### 7.2 Post-Hoc Observability (Archives)

Every workflow produces a timestamped zip archive in `./logs/archive/`:
- `manifest.json` — routing_history, timestamps, run metadata, parent_run_id for child forks
- `llm_traces.jsonl` — per-specialist execution with latency_ms
- `final_state.json` — accumulated state at workflow end
- `state_timeline.jsonl` — state snapshots at each specialist boundary

**The archive is authoritative.** If the UI shows something different, the bug is in the UI layer.

### 7.3 Observability Stack

| Layer | Tool | Purpose |
|-------|------|---------|
| Tracing | LangSmith `@traceable` | Hierarchical specialist execution spans |
| Streaming | AgUiTranslator → SSE | Real-time events to web UI |
| Progress | progress_store → polling | Intra-node updates during long ReAct loops |
| Archive | ArchiverSpecialist | Atomic post-hoc workflow packages |
| Logging | Python `logging` | Structured operational logs |

---

## 8. LLM Adapters

Factory pattern with provider abstraction:

| Adapter | Provider | Notes |
|---------|----------|-------|
| `PooledLMStudioAdapter` | Local (multi-GPU) | Primary. Extends LMStudioAdapter with local-inference-pool for rtx8000 + rtx3090 routing, JIT-swap guard, least-loaded balancing (ADR-068) |
| `LMStudioAdapter` | Local (single server) | Base class for pooled adapter |
| `GeminiAdapter` | Google | Cloud provider |
| `AnthropicAdapter` | Anthropic | Cloud provider |
| `OpenAIAdapter` | OpenAI | Cloud provider |

**Model agnosticism:** The system works with 20+ models. No specialist depends on specific model behaviors. All model bindings are runtime configuration (`user_settings.yaml`).

---

## 9. Configuration

```
.env              → Secrets (API keys, never committed)
config.yaml       → Structure (specialists, providers, MCP)
user_settings.yaml → Bindings (which model for which specialist)
```

Separation allows the same structure with different runtime bindings. Supports `${VAR_NAME}` and `${VAR_NAME:-default}` interpolation.

---

## 10. Specialist Inventory

### Core Infrastructure (6)
- `BaseSpecialist` — Abstract base
- `RouterSpecialist` — Central routing hub (deterministic greeting gate + LLM routing)
- `EndSpecialist` — Termination and synthesis
- `ArchiverSpecialist` — Atomic workflow archives
- `TriageArchitect` — Entry pipeline classifier
- `SystemsArchitect` — Entry point (task_plan) + MCP planning service

### Context Engineering (3)
- `FacilitatorSpecialist` — Context assembly, EI feedback surfacing, BENIGN continuation (procedural)
- `ExitInterviewSpecialist` — Completion verification via react_step MCP tools
- `SignalProcessorSpecialist` — Interrupt classification and routing (ADR-077)

### Autonomous Agents (1)
- `ProjectDirector` — ReAct agent for filesystem/research tasks (filesystem, terminal, fork with expected_artifacts, live progress publishing)

### Analysis (1)
- `TextAnalysisSpecialist` — ReAct-enabled: single-pass analysis or iterative tool use (filesystem, terminal, semantic-chunker, it-tools MCP)

### Chat & Response (6)
- `ChatSpecialist` — Simple chat
- `ProgenitorAlpha/Bravo` — Parallel perspectives (tiered chat subgraph)
- `TieredSynthesizer` — Combines perspectives (procedural join node)
- `DefaultResponder` — Greetings
- `SummarizerSpecialist` — Text condensation

### Generation (2)
- `WebBuilder` — HTML generation
- `CriticSpecialist` — Artifact review (generate-critique-refine loop)

### Browser (1)
- `NavigatorBrowserSpecialist` — surf-mcp integration

### Other (2)
- `ImageSpecialist` — Image analysis
- `TribeConductor` — Convening orchestration

**Active in config.yaml: ~20 specialists.**

---

## 11. Test Coverage

- **Unit tests:** 964 tests (mocked LLM calls), 2 known skipped (#192)
- **Integration tests:** ~178 tests (real configs, live LLM)
- **Concurrent invocation tests:** 15 tests verifying shared mutable state integrity under concurrent fork()
- **Total:** 1,150+ tests

---

## 12. Key Files

| File | Purpose |
|------|---------|
| `graph_orchestrator.py` | Interrupt classification, routing logic |
| `graph_builder.py` | Adapter wiring, edge registration |
| `context_engineering.py` | Entry pipeline (Triage → SA → Facilitator → Router) |
| `specialist_categories.py` | CORE_INFRASTRUCTURE, MCP_ONLY, exclusions |
| `facilitator_specialist.py` | Context assembly, EI feedback surfacing |
| `project_director.py` | Autonomous ReAct agent with progress publishing |
| `text_analysis_specialist.py` | Dual-mode (single-pass + react_step MCP) |
| `lmstudio_adapter.py` | Tool call parsing, request building |
| `pooled_adapter.py` | Multi-GPU pool routing |
| `factory.py` | AdapterFactory, pool lifecycle |
| `config_loader.py` | Server name resolution, env var injection |
| `mcp/react_step.py` | Shared ToolDef, call_react_step, build_tool_schemas |
| `mcp/fork.py` | dispatch_fork, extract_fork_result, conditioning frame |
| `state.py` | GraphState definition, reducers |
| `node_executor.py` | SafeExecutor wrapper |
| `utils/progress_store.py` | Thread-safe intra-node progress publishing |

---

## 13. Research Connections

LAS serves as a workbench for studying how orchestration-layer interventions shape model behavior without touching weights:

- **Prompt geometry:** semantic-chunker measures phrasing geometry in embedding space. RLHF shapes response space by making regions "cold" — phrasings geometrically distant from trained forms may hit unexplored regions.
- **Explicit MoE as interpretability tool:** Specialist routing decisions are observable analogs of implicit MoE expert selection. TransformerLens residual stream analysis can compare LAS's explicit gating with the same models' internal routing.
- **Semantic contrast:** Prompt decision-point quality measured via embedding-space drift between branches. Higher pairwise drift between decision options → sharper model decision boundaries.
- **Context engineering as physics:** Token positions create query-key geometries that determine inference trajectories. Facilitator constructs the experiential reality for each inference pass — what it places where determines what the model attends to.

See `docs/ADRs/` for architectural decisions and design documentation.
