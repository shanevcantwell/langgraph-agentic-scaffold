# LAS v1.0 Architecture Reference

> Definitive reference for LAS 1.0 ("Project Bedrock Complete") to inform LAP (LAS 2.0) design.

---

## 1. Identity

**LAS** (langgraph-agentic-scaffold) is a Python orchestration framework for multi-model agentic workflows with structural safety constraints.

**Core thesis:** frontier LLMs are unreliable and possibly manipulative. The framework must enforce safety through structure, not trust.

---

## 2. Architectural Primitives

### 2.1 GraphState
Central state object passed between all nodes. Uses `Annotated` types for merge behavior.

```python
messages: Annotated[list, operator.add]      # Append-only conversation
artifacts: Annotated[dict, operator.ior]     # Dict merge for outputs
scratchpad: dict                             # Ephemeral signals (cleared after routing)
routing_history: list                        # Execution path tracking
turn_count: int                              # Recursion control
```

**Key insight:** Scratchpad is ephemeral (signals), artifacts are persistent (outputs).

### 2.2 BaseSpecialist
All specialists inherit from `BaseSpecialist`. Contract:
- `_execute_logic(state) -> dict` - Core logic, returns state updates
- `_perform_pre_flight_checks() -> bool` - Validation before execution
- `register_mcp_services(registry)` - Optional MCP service exposure

**Key insight:** Specialists never mutate state directly. They return dicts that the executor merges.

### 2.3 NodeExecutor (SafeExecutor)
Wraps all specialist execution. Responsibilities:
- Invariant checking (pre/post execution)
- Error isolation
- Circuit breaker triggering
- LangSmith tracing

**Key insight:** No specialist can bypass safety. All execution flows through this wrapper.

### 2.4 MCP (Message-Centric Protocol)
Synchronous service invocation between specialists. Two types:
- **Internal MCP:** Python functions registered in `McpRegistry`
- **External MCP:** Containerized services via stdio JSON-RPC

```python
# Internal
result = self.mcp_client.call("file_specialist", "read_file", path="...")

# External
result = sync_call_external_mcp(client, "navigator", "goto", {"url": "..."})
```

**Key insight:** MCP is for deterministic service calls. Dossier pattern is for LLM-driven handoffs.

---

## 3. Routing Architecture

### 3.1 Hub-and-Spoke
Router is the central hub. All specialists return to router after execution.

```
User → Triage → SA → Facilitator → Router → Specialist → Router → ... → End
```

### 3.2 Subgraphs
Encapsulated multi-specialist workflows that appear as single nodes to the router:
- **Tiered Chat:** Alpha ∥ Bravo → Synthesizer
- **Context Engineering:** Triage → SA → Facilitator → Router (#199)
- **Signal Processor:** Detects and routes interrupt signals (max_iterations, stagnation, etc.)

### 3.3 Routing Decisions
Three routing modes:
1. **Declarative:** Explicit `next_specialist` in scratchpad
2. **Procedural:** Decider functions in `GraphOrchestrator`
3. **Probabilistic:** Router LLM chooses based on capability descriptions

---

## 4. Core Flows

### 4.1 Context Engineering (Pre-flight, #199)
```
User Request
    ↓
TriageArchitect ──→ ACCEPT/REJECT gate (classifier)
    ↓ [PASS]
SystemsArchitect ──→ Produces task_plan (with acceptance_criteria)
    ↓
Facilitator ──→ Assembles gathered_context (always runs)
    ↓
Router ──→ Routes with gathered_context available
```

**Purpose:** Gate, plan, and gather context before routing so specialists have what they need.

### 4.2 Tiered Chat (CORE-CHAT-002)
```
Router
    ↓
┌───────┬───────┐
│ Alpha │ Bravo │  (parallel, different models)
└───┬───┴───┬───┘
    ↓       ↓
TieredSynthesizer ──→ Combines perspectives
    ↓
End
```

**Purpose:** Multi-model adversarial validation. Different providers reduce correlated errors.

### 4.3 Generate-Critique-Refine
```
WebBuilder ──→ Creates artifact
    ↓
Critic ──→ Reviews, returns ACCEPT or REVISE
    ↓
[REVISE] → WebBuilder (loop, max 3)
[ACCEPT] → End
```

**Purpose:** Self-improvement loop with explicit termination.

### 4.4 ReAct Tool Use (react_step MCP)
```
Specialist with tools: config
    ↓
┌─────────────────────────────────────────┐
│ Loop until DONE (via call_react_step):  │
│   1. call_react_step() → prompt-prix    │
│   2. prompt-prix makes LLM call         │
│   3. Specialist dispatches tool calls   │
│   4. Append observations to trace       │
│   5. Check max_iterations               │
└─────────────────────────────────────────┘
    ↓
Specialist writes artifacts + signals task_is_complete
```

**Purpose:** Iterative tool use with LLM-in-the-loop control.

**Current consumers:** ProjectDirector (filesystem/terminal), TextAnalysisSpecialist (semantic-chunker/it-tools), ExitInterview (filesystem/artifact tools).

**Shared helper pattern:** `app/src/mcp/react_step.py` provides `ToolDef` + `call_react_step` + `build_tool_schemas` + `dispatch_external_tool`. Any specialist becomes ReAct-capable by defining a tool routing table and looping on `call_react_step()`. No config flag, no wrapper, no mixin.

**ReActMixin deleted:** The former ~1700-line `ReActMixin` / `ReactEnabledSpecialist` / `react_wrapper.py` was replaced by prompt-prix MCP's `react_step()` primitive (Phase 5, #162). -1720 lines net.

---

## 5. Safety Mechanisms

### 5.1 Invariant Monitor
Checks system health before each specialist execution:
- State structure validity
- Max turn count (recursion limit)
- Loop detection (A→B→A→B pattern)

Violations trigger circuit breaker → stabilization action (HALT or ROUTE_TO_ERROR).

### 5.2 Fail-Fast Validation
- **Startup:** Critical specialists must load or app fails
- **Routing:** Unknown destinations raise `WorkflowError`

### 5.3 Four-Stage Termination
Human control preserved:
1. Specialist produces artifacts
2. Exit Interview evaluates completion (ADR-CORE-036)
3. End specialist synthesizes final response
4. Archiver records to atomic package

No specialist can unilaterally terminate.

---

## 6. Observability Hooks

| Hook | Location | Purpose |
|------|----------|---------|
| `@traceable` | Specialists, MCP | LangSmith trace spans |
| `AgUiEmitter` | API | SSE events to UI |
| `logger.*` | Everywhere | Structured logging |
| `TrainingCapture` | BaseSpecialist | Training data collection |
| `ArchiverSpecialist` | End of flow | Workflow reports to disk |

**Gap:** No unified observability strategy. Hooks exist but aren't cohesive.

---

## 7. External Integrations

### 7.1 LLM Adapters
Factory pattern with provider abstraction:
- `PooledLMStudioAdapter` (local models via GPU pool — primary, ADR-068)
- `LMStudioAdapter` (local models, single server — base class for pooled)
- `GeminiAdapter` (Google)
- `AnthropicAdapter` (Claude)
- `OpenAIAdapter` (GPT)

`PooledLMStudioAdapter` extends `LMStudioAdapter` with `local-inference-pool` for multi-GPU routing (rtx8000 + rtx3090), JIT-swap guard, and least-loaded balancing.

### 7.2 External MCP Containers
- **filesystem:** File read/write/list operations
- **terminal:** Shell command execution (run_command, get_cwd)
- **surf-mcp:** Browser automation with Fara visual grounding
- **semantic-chunker:** Embedding analysis — embeddinggemma-300m (768-d) default, NV-Embed-v2 (4096-d) available (calculate_drift, classify_document, analyze_variants)
- **it-tools-mcp:** 119 IT utility tools (format_json, convert_json_to_csv, etc.)
- **prompt-prix-mcp:** Eval primitives (react_step, complete, list_models) — operational, 9 tools via FastMCP

### 7.3 prompt-prix Integration (Eval)
Two containers from the same image, different purposes:
- **prompt-prix-mcp:** Thin MCP server for iteration primitives. LAS calls via `sync_call_external_mcp()`.
- **prompt-prix (app):** Full application for battery evaluation. LAS calls via internal MCP tool wrapping `docker exec prompt-prix prompt-prix-cli run-battery ...`.

Battery runs go through the CLI (full app), not MCP. Model/adapter routing is prompt-prix's responsibility — LAS is model-agnostic at the eval boundary.

### 7.4 Search Strategies
Fallback chain: Brave → DuckDuckGo → (future: more)

---

## 8. Configuration Tiers

```
.env              → Secrets (API keys, never committed)
config.yaml       → Structure (specialists, providers, MCP)
user_settings.yaml → Bindings (which model for which specialist)
```

**Key insight:** Separation allows same structure with different runtime bindings.

### 8.1 Specialist Menu Exclusions (ADR-CORE-053)

Control which specialists appear in triage menus via config-driven exclusions:
- `excluded_from: [triage_architect]` - Hide specialist from specific menus
- `TRIAGE_INFRASTRUCTURE` - Built-in exclusions (router, archiver, end, critic)
- `SpecialistCategories.get_triage_exclusions()` - Centralized exclusion logic

See CONFIGURATION_GUIDE.md § 5.0 for details.

---

## 9. What Works Well (Keep for LAP)

| Pattern | Why It Works |
|---------|--------------|
| SafeExecutor wrapper | Enforces safety structurally |
| Scratchpad/Artifacts split | Clear ephemeral vs persistent semantics |
| MCP for services | Clean synchronous invocation |
| Subgraph encapsulation | Complex flows as single nodes |
| Tiered parallel progenitors | Multi-model reduces correlated errors |
| Context engineering pre-flight | Specialists get context they need |
| Invariant monitor | Catches loops and corruption |

---

## 10. What's Awkward (Fix in LAP)

| Issue | Problem | LAP Direction |
|-------|---------|---------------|
| ~20 specialists | Consolidated from 37+ via Phase 1b | Further extraction to MCP containers |
| Deprecated source files | Some deprecated .py files remain | Clean removal pass needed |
| Documentation bloat | 17 docs, much redundancy | Single authoritative reference |
| Observability fragmentation | Hooks exist but not unified | Cohesive observability layer |
| Deep agent lifecycle | Not implemented (ADR-CORE-038) | First-class in LAP |
| Model registry | Duplicated across projects | Shared MCP service (ADR-CORE-039) |
| WebUI adapters | Fragile DOM scraping | Visual grounding via surf-mcp |

---

## 11. Specialist Inventory

### Core Infrastructure (6)
- `BaseSpecialist` - Abstract base
- `RouterSpecialist` - Central routing hub
- `EndSpecialist` - Termination and synthesis
- `ArchiverSpecialist` - Workflow reports
- `TriageArchitect` - Context engineering entry (classifier)
- `SystemsArchitect` - Entry point (task_plan) + MCP planning service (#171)

### Context Engineering (2)
- `FacilitatorSpecialist` - Context assembly, EI feedback surfacing (procedural)
- `ExitInterviewSpecialist` - Completion verification via react_step MCP tools

### Chat & Response (6)
- `ChatSpecialist` - Simple chat
- `ProgenitorAlpha/Bravo` - Parallel perspectives (tiered chat subgraph)
- `TieredSynthesizer` - Combines perspectives (procedural join node)
- `DefaultResponder` - Greetings
- `SummarizerSpecialist` - Text condensation

### Autonomous Agents (1)
- `ProjectDirector` - ReAct agent for filesystem/research tasks via react_step MCP (filesystem, terminal, fork with expected_artifacts)

### Analysis (1)
- `TextAnalysisSpecialist` — ReAct-enabled: single-pass analysis or iterative tool use (filesystem, terminal, semantic-chunker, it-tools MCP). Absorbed DataExtractor and DataProcessor (Phase 1b).

### Generation (2)
- `WebBuilder` - HTML generation
- `CriticSpecialist` - Artifact review

### Browser (1)
- `NavigatorBrowserSpecialist` - surf-mcp integration

### Other (2)
- `ImageSpecialist` - Image analysis
- `TribeConductor` - Convening orchestration

**Active in config.yaml: ~20 specialists.** Deprecated specialists (FileSpecialist, NavigatorSpecialist, DataExtractor, DataProcessor, ResearchOrchestrator, Distillation pipeline) removed from config; some source files remain with deprecation notices.

---

## 12. Test Coverage

- **Unit tests:** 964 tests (mocked LLM calls), 2 known skipped (#192)
- **Integration tests:** ~178 tests (real configs, some live LLM)
- **Total:** 1140+ tests

Key test patterns:
- Contract validation via Pydantic
- State transition verification
- Subgraph wiring tests
- MCP service tests

---

## 13. Project Bedrock Status

**100% complete (37/37 tasks)**

| Workstream | Status |
|------------|--------|
| 1. Foundational Resilience | ✅ Complete |
| 2. Explicit Control Plane (MCP) | ✅ Complete |
| 3. Hybrid Routing Engine | ✅ Complete |
| 4. Platform & Tooling | ✅ Complete |
| 5. Context Engineering | ✅ Complete |

Post-Bedrock additions:
- react_step MCP (replaced ReActMixin — prompt-prix absorption, -1720 lines net)
- Navigation-MCP (now surf-mcp)
- V.E.G.A.S. Terminal UI
- fork() — recursive LAS invocation via graph.invoke() for context-isolated subtasks, with conditioning frame (#205) and expected_artifacts (#206)
- SystemsArchitect entry point (#171) — SA → Triage → Facilitator → Router pipeline
- it-tools-mcp — 119 IT utility tools wired to TextAnalysisSpecialist

---

## 14. LAP Design Implications

Based on LAS v1.0 experience:

1. **Organism Model:** LAS is Brain (Codex) + Spine (control plane). Specialists become MCP containers ("organs").

2. **Deep Agent Lifecycle:** First-class spawn/pause/resume/terminate for long-running agents.

3. **Model Registry MCP:** Shared service discovery across LAS, prompt-prix, surf-mcp.

4. **Unified Observability:** Single strategy for tracing, events, logging, capture.

5. **Documentation as Code:** Generate docs from code structure, not maintain separately.

---

*This document supersedes: ARCHITECTURE.md, HAPPY_PATHS.md, GRAPH_VISUALIZATIONS.md, and various orphan pattern docs for LAP planning purposes.*
