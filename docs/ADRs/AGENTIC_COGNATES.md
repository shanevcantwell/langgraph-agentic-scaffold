# Agentic Cognates: Computing Metaphors for LLM Agency

**Date:** 2025-12-20
**Purpose:** Catalog mappings between computing/software concepts and agentic patterns to identify gaps and unknown unknowns.

---

## Rationale

LLM agents operate within constraints similar to classical computing:
- Limited working memory (context window)
- Need for persistence across invocations
- Coordination between multiple execution units
- Resource contention and scheduling

By systematically mapping computing concepts to agentic patterns, we can:
1. Identify proven patterns to adapt
2. Discover gaps in our architecture
3. Provide intuitive mental models for developers
4. Find unknown unknowns by examining what's missing

---

## Established Cognates

These mappings are explicitly documented in LAS ADRs.

### Memory Hierarchy

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **Stack** | Scratchpad / Context Window | CORE-022, 023 | Fast, ephemeral, per-invocation working memory |
| **Heap** | Artifacts / Manifest | CORE-022 | Persistent, shared, survives invocations |
| **Registers** | Active reasoning state | CORE-023 | Immediate execution context |
| **Cache** | Context Snippets / Summarization Gates | CORE-022, 031 | Compressed representation of larger data |
| **Virtual Memory** | Context window + Heap paging | CORE-022 | Illusion of larger memory via swapping |

### Execution Model

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **CPU/Scheduler** | RouterSpecialist | ARCH §2.0 | Turn-by-turn routing decisions in main loop |
| **Kernel** | NodeExecutor / GraphBuilder | ARCH §2.0 | Infrastructure that runs specialists, enforces invariants |
| **Dispatcher** | TriageArchitect | ARCH §6.0 | Analyzes requests, dispatches to appropriate capability |
| **Loader** | FacilitatorSpecialist | ARCH §6.3 | Loads context before main execution |
| **Context Switch** | dereference_branch() / commit_branch() | CORE-023 | Save/restore agent state to/from Heap |
| **Process** | Specialist invocation | — | Isolated execution unit with own context |
| **Thread Pool** | Progenitors (TieredChat) | ARCH §4.0 | Parallel workers with join node |
| **Interrupt** | HitL via DialogueSpecialist | CORE-018 | External event pauses graph for input |
| **Trap/Exception** | InvariantMonitor violation | ARCH §5.0 | Hardware-style interrupt on invariant failure |
| **Main Loop** | Router → Specialist → Router | ARCH §2.0 | Graph's primary execution cycle |

**Note:** TribeConductor (CORE-023) is a *higher-level orchestration policy* that uses these primitives for multi-model collaboration, not the scheduler itself.

### Control Flow

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **while()** | Critic subgraph / IRP loop | CORE-012, CORE-031 | Iterate until condition met |
| **for()** | FacilitatorSpecialist (ContextActions) | ARCH §6.3 | Iterate over action list |
| **for()** | BatchSpecialist | — | Iterate over collection |
| **Internal Loop (no graph hop)** | ReActMixin `execute_with_tools()` | CORE-029 | LLM → tool → LLM → ... within single specialist |
| **Local Jump (bypass scheduler)** | Critic Subgraph direct edges | CORE-012 | Direct edges between nodes, bypassing Router |
| **State Machine (deterministic)** | LangGraph conditional edges | ARCH §3.4 | Predefined transitions with defined edges |
| **Emergent State Machine** | Router semantic classification | ARCH §2.0 | LLM-driven transitions based on semantic classification |
| **Instruction Decoder** | Router classifier | ARCH §2.0 | Classifies input → determines specialist transition |
| **Function Call** | MCP service invocation | ARCH §7.0 | Synchronous call to another capability |
| **System Call** | MCP call from specialist to infrastructure | ARCH §7.0 | Specialist → infrastructure service |
| **Return Value** | Scratchpad / Artifacts | ARCH §2.1 | Structured handoff between specialists |
| **Page Fault** | Context gathering trigger | ARCH §6.0 | Insufficient context → triggers Facilitator |

### Process Lifecycle

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **Suspend/Resume** | Checkpointer save/restore | CORE-018, ARCH §6.2 | SqliteSaver/PostgresSaver state persistence |
| **Process Serialization** | Checkpointer + GraphState snapshot | CORE-018 | Persist process state across API calls |
| **Compile-time vs Runtime** | GraphBuilder vs Runner | ARCH §2.0 | Graph setup vs execution |
| **Cycle Detection** | InvariantMonitor 2-step check | ARCH §5.1 | Detect and break runaway loops |
| **Graceful Degradation** | ReActMixin `MaxIterationsExceeded` | CORE-029 | Synthesize partial results on iteration limit |

**Note:** RECESS blueprint proposed Hydrate/Execute/Dehydrate pattern; LAS implements this via Checkpointer + ReActMixin graceful degradation.

### Concurrency

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **Fork/Join** | TieredChat (Progenitors + Synthesizer) | ARCH §4.0 | Fan-out to parallel nodes, join at synthesizer |
| **Critical Section** | Fishbowl debate | CORE-023 | Synchronous, exclusive multi-turn interaction |
| **Message Queue** | GraphState messages list | ARCH §2.1 | Append-only message history |
| **Shared Memory** | Artifacts dict | ARCH §2.1 | Cross-specialist structured data |
| **Graceful Degradation** | TieredSynthesizer fallback modes | ARCH §4.5 | Continue with partial results |

### I/O and Safety

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **Firewall** | Semantic Firewall | CORE-023 | Filter I/O between trust boundaries |
| **Sanitization** | Input validation + output compression | CORE-023 | Prevent injection, strip low-value content |
| **Checksum/Hash** | Hash chain in Manifest | CORE-022 | Integrity verification |
| **Circuit Breaker** | InvariantMonitor | ARCH §5.0 | Fail-fast on invalid state, loop detection |

### Observability

| Computing Concept | Agentic Cognate | ADR | Description |
|-------------------|-----------------|-----|-------------|
| **Profiler** | LangSmith integration | ARCH §9.0 | Token counts, latency, costs per LLM call |
| **Debugger** | Forensic logging + Archive reports | ARCH §9.2-9.3 | Trace execution, state snapshots |
| **Checkpointing** | SqliteSaver / PostgresSaver | CORE-018, ARCH §6.2 | Persist graph state for resume/rollback |

---

## Implied Cognates

These patterns exist in LAS but aren't explicitly framed as cognates.

| Computing Concept | Potential LAS Mapping | Status | Notes |
|-------------------|----------------------|--------|-------|
| **Mutex/Semaphore** | Resource contention for parallel specialists | Gap | What happens if two specialists need same artifact? |
| **Garbage Collection** | Stale branch cleanup | Partial (023) | Staleness detection exists, but not automatic cleanup |
| **Bus** | MCP service registry | Implemented | Central communication backbone (ARCH §7.0) |
| **DMA** | Direct artifact access (bypass context) | Proposed | See "DMA-Enabled Specialists" below |
| **Compiler** | Prompt template construction | Implied | Translating high-level intent to executable prompt |
| **Linker** | Semantic Linker middleware | Proposed | See "Semantic Linker" below → ADR-CORE-034 |
| **Symbol Table** | ManifestManager.branches | Implemented | Branch ID → filepath + context_snippet (app/src/utils/manifest_manager.py) |
| **Filesystem** | ManifestManager + branch files | Implemented | Manifest = index, branch files = content (ADR-CORE-022) |
| **JIT** | Dynamic prompt compilation | Proposed | See "JIT Prompt Compilation" below |
| **Bootloader** | Graph compilation (GraphBuilder) | Implemented | Initialize system before execution (ARCH §2.0) |
| **Watchdog Timer** | Max turn count enforcement | Implemented | Kill runaway execution (ARCH §5.1) |

---

## Unexplored Cognates (Unknown Unknowns)

Computing concepts that might have valuable agentic applications but aren't yet mapped.

### Memory Management

| Concept | Potential Application | Priority |
|---------|----------------------|----------|
| **Reference Counting** | Track artifact usage, auto-cleanup when unused | Medium |
| **Copy-on-Write** | Lazy artifact duplication for parallel branches | Low |
| **Memory Pool** | Pre-allocated context budget across specialists | Medium |
| **Fragmentation** | Context window fragmentation from many small artifacts | Research |

### Execution

| Concept | Potential Application | Priority |
|---------|----------------------|----------|
| **Coroutines** | Cooperative multitasking between specialists | Medium |
| **Futures/Promises** | Async artifact resolution | Medium |
| **Lazy Evaluation** | Defer artifact loading until needed | High |
| **Memoization** | Cache expensive LLM calls by input hash | High |
| **Tail Call Optimization** | Efficient specialist chaining without stack growth | Low |
| **Speculative Execution** | Start likely-next specialist while Router decides | High |

### Distributed Systems

| Concept | Potential Application | Priority |
|---------|----------------------|----------|
| **Consensus Protocol** | Multi-model agreement (beyond Fishbowl) | Medium |
| **Eventual Consistency** | Allow temporary divergence between branches | Research |
| **Leader Election** | Dynamic TribeConductor selection | Low |
| **Sharding** | Partition large tasks across specialist groups | Medium |
| **Circuit Breaker** | InvariantMonitor with fail-fast | Done (ARCH §5.0) |

### Reliability

| Concept | Potential Application | Priority |
|---------|----------------------|----------|
| **Checkpointing** | SqliteSaver/PostgresSaver for graph state | Done (018, ARCH §6.2) |
| **Rollback** | Checkpoint-based state restore | Partial (via checkpointing) |
| **Transaction Log** | Contribution log with replay capability | Partial (022) |
| **Idempotency** | Safe retry of specialist invocations | Gap |
| **Dead Letter Queue** | Failed specialist outputs for review | Gap |

### Compilation/Optimization

| Concept | Potential Application | Priority |
|---------|----------------------|----------|
| **JIT Compilation** | Dynamic prompt compilation based on GraphState | High |
| **Static Analysis** | Pre-flight validation of specialist chains | Medium |
| **Tree Shaking** | Remove unused artifacts from context | Medium |
| **Inlining** | Embed small specialist logic directly | Low |

---

## Proposed Architectural Extensions

Concrete implementations derived from cognate analysis. These extend LAS from "Runtime" toward "Operating System."

### 1. Semantic Linker (HIGH PRIORITY)

**Computing Cognate:** Linker (symbol resolution)

**Problem:** Agents "hallucinate" links. Router passes `{"target": "that marketing report"}`, specialist burns tokens searching or guessing. This is a runtime symbol resolution error.

**Solution:** Middleware between Router and Specialist that resolves symbolic references.

```
Router → [Semantic Linker] → Specialist
              ↓
         ManifestManager
         (Symbol Table)
```

**Implementation:**
```python
class SemanticLinker:
    """Resolve symbolic references to concrete artifact paths."""

    def __init__(self, manifest: ManifestManager):
        self.manifest = manifest  # Already implemented: app/src/utils/manifest_manager.py

    def resolve(self, state: GraphState) -> GraphState:
        """Intercept state, resolve fuzzy references to UUIDs/paths."""
        scratchpad = state.get("scratchpad", {})

        # Find unresolved references
        if target := scratchpad.get("target"):
            if not self._is_concrete(target):
                resolved = self.manifest.fuzzy_match(target)  # NEW: add fuzzy_match()
                scratchpad["target"] = resolved.path
                scratchpad["_resolved_from"] = target  # Audit trail

        return {**state, "scratchpad": scratchpad}
```

**Existing Infrastructure:**
- `ManifestManager` IS the symbol table (`manifest.branches` maps ID → filepath + context_snippet)
- Missing: `fuzzy_match()` method for semantic resolution
- Missing: Middleware integration point between Router and Specialist

**Benefit:** Specialist receives `target: "report_2025_v2.md"`. Zero ambiguity, zero search tokens.

**Status:** Partial → Extend ManifestManager with fuzzy_match(), add middleware. See ADR-CORE-034

### 2. DMA-Enabled Specialists (MEDIUM PRIORITY)

**Computing Cognate:** Direct Memory Access

**Problem:** To analyze large files, agents read chunks into context window (CPU registers), process, repeat. Causes context thrashing.

**Solution:** Specialists support "DMA Mode" — execute queries on data without loading to context.

```python
# Current (loads to context):
content = file_specialist.read_file("logs/app.log")  # 50K tokens
matches = llm.analyze(content, "find errors")

# DMA Mode (never loads to context):
matches = file_specialist.scan_file(
    path="logs/app.log",
    query="grep -E 'ERROR|FATAL'",  # Executed by infrastructure
)  # Returns 200 tokens
```

**Cognate insight:** LLM as Control Unit (orchestrates data flow), not ALU (crunches bytes).

**Status:** Partial — some tools do this, but not formalized as pattern

### 3. Speculative Routing / Branch Prediction (RESEARCH)

**Computing Cognate:** CPU Branch Prediction

**Problem:** RouterSpecialist is expensive/slow (von Neumann bottleneck). Waiting for Router after Triage introduces latency.

**Solution:** If TriageArchitect recommends specialist with high confidence:

```python
class SpeculativeOrchestrator:
    def route(self, state, triage_result):
        if triage_result.confidence > 0.9:
            # Fork: start speculative execution
            speculative_future = self.executor.submit(
                triage_result.recommended_specialist,
                state
            )

        # Verify: run Router
        router_decision = self.router.decide(state)

        if router_decision == triage_result.recommended_specialist:
            # Attach already-running process
            return speculative_future.result()
        else:
            # Discard speculative branch
            speculative_future.cancel()
            return self.execute(router_decision, state)
```

**Trade-off:** Tokens (speculative compute) for latency (speed).

**Status:** Research — requires cost/benefit analysis

### 4. JIT Prompt Compilation (HIGH PRIORITY)

**Computing Cognate:** Just-In-Time Compilation

**Problem:** Agents use "interpreted" prompts — static blocks covering every case. Wastes tokens, dilutes attention.

**Solution:** NodeExecutor JIT-compiles prompts based on GraphState.

```python
class PromptJIT:
    """Compile prompts dynamically based on execution context."""

    def compile(self, template: str, state: GraphState) -> str:
        """Remove irrelevant sections, specialize for current turn."""
        compiled = template

        # If no artifacts, remove artifact instructions
        if not state.get("artifacts"):
            compiled = self._remove_section(compiled, "## Updating Existing Artifacts")

        # Platform-specific
        if state.get("platform") == "windows":
            compiled = self._remove_section(compiled, "### Linux Examples")

        # Task-specific: if this is a read-only query, remove write instructions
        if state.get("scratchpad", {}).get("read_only"):
            compiled = self._remove_section(compiled, "## Writing Files")

        return compiled
```

**Result:** 40% smaller prompts, 2x more accurate for specific turn.

**Status:** Gap → should integrate with existing prompt loading

---

## Gap Analysis

### High-Priority Gaps (With Proposed Solutions)

1. **Semantic Linker** ← HIGHEST PRIORITY
   - Problem: Agents hallucinate artifact references, burn tokens searching
   - Solution: ManifestManager-backed fuzzy match middleware
   - Existing: `ManifestManager` is the symbol table (branches → filepath)
   - Missing: `fuzzy_match()` method + Router→Specialist middleware
   - Benefit: Zero-ambiguity specialist input
   - Status: **Partial → ADR-CORE-034** (extend existing infrastructure)

2. **JIT Prompt Compilation**
   - Problem: Static prompts waste tokens on irrelevant instructions
   - Solution: Compile prompts dynamically based on GraphState
   - Benefit: 40% smaller prompts, improved accuracy
   - Status: **Proposed** (see Architectural Extensions above)

3. **Memoization/Caching**
   - Problem: Expensive LLM calls repeated with same/similar inputs
   - Solution: Hash-based cache with semantic similarity matching
   - Benefit: Cost and latency reduction

4. **Lazy Evaluation**
   - Problem: Context filled with artifacts that may not be needed
   - Solution: Load artifacts on-demand, not upfront
   - Benefit: Context efficiency

### Medium-Priority Gaps

5. **DMA-Enabled Specialists**
   - Problem: Large file analysis causes context thrashing
   - Solution: Execute queries on data without loading to context
   - Status: **Proposed** (see Architectural Extensions above)

6. **Idempotency**
   - Ensure specialist re-invocation is safe

7. **Static Analysis**
   - Validate specialist chains before execution

8. **Artifact Versioning**
   - Full rollback beyond checkpoint-based restore
   - Version history for individual artifacts

### Research-Priority

9. **Speculative Routing**
   - Trade tokens for latency via branch prediction
   - Status: Requires cost/benefit analysis

### Already Implemented (Previously Mislabeled as Gaps)

- **Circuit Breaker** — InvariantMonitor (ARCH §5.0)
- **Profiler/Observability** — LangSmith integration (ARCH §9.0)
- **Checkpointing/Rollback** — SqliteSaver/PostgresSaver (ARCH §6.2)

---

## ADR Mapping

### Currently Documented Cognates by ADR

| ADR | Computing Cognates |
|-----|-------------------|
| CORE-012 (Critic Subgraph) | while() loop, Local Jump (direct edges) |
| CORE-018 (HitL) | Suspend/Resume, Process Serialization |
| CORE-022 (Heap) | Heap memory, Virtual Memory, Cache |
| CORE-023 (Convening) | Thread Pool, Fork/Join, Critical Section |
| CORE-027 (Navigation-MCP) | Function Call, RPC, Session State |
| CORE-029 (ReActMixin) | Internal Loop, Graceful Degradation |
| CORE-031 (IRP) | while() loop, Coroutines |

### Proposed New ADRs

| ADR | Cognate | Description | Status |
|-----|---------|-------------|--------|
| **CORE-034** | Linker | Semantic Linker — extends ManifestManager, adds middleware | CREATED |
| **CORE-035** | JIT | Prompt JIT Compilation — dynamic prompt optimization | TODO |
| **CORE-036** | DMA | DMA-Enabled Specialists — query-mode file access | TODO |

### Cognates to Document in Future ADRs

| ADR | Cognates to Add |
|-----|-----------------|
| CORE-022 (Heap) | Reference Counting (artifact cleanup) |
| Future: CORE-0XX | Memoization, Lazy Eval, Idempotency, Speculative Execution |

---

## Design Questions

1. **Should cognate framing be required in ADRs?**
   - Pro: Systematic coverage, identifies gaps
   - Con: May force-fit concepts that don't map cleanly

2. **Which gaps are most urgent?**
   - Memoization for cost control
   - Lazy Evaluation for context efficiency
   - Idempotency for reliability

3. **Are there agentic patterns with NO computing cognate?**
   - Multi-model adversarial validation (closest: Byzantine fault tolerance?)
   - Semantic judgment (closest: heuristic functions?)
   - Prompt injection defense (closest: input sanitization, but semantic layer is novel)
   - **Emergent State Machine** inverts traditional FSM: transitions are semantic, not deterministic
   - **Artifact-Driven Bias** (RECESS) — prioritizing concrete proposals over abstract questions

---

## References

### Implemented ADRs (Primary Sources)
- ADR-CORE-012: Web Builder ↔ Critic Subgraph (direct edges, generate-critique-refine)
- ADR-CORE-018: Human-in-the-Loop Integration (checkpointing, pause/resume)
- ADR-CORE-022: The Heap (artifact persistence, context snippets)
- ADR-CORE-023: Convening of the Tribes (orchestration policy, Fishbowl)
- ADR-CORE-027: Navigation-MCP (browser automation, session persistence)
- ADR-CORE-029: ReActMixin Deep Research (internal iteration, graceful degradation)
- ADR-CORE-031: Iterative Reasoning Pattern (generate → compress → evaluate)

### Architecture Documentation
- docs/ARCHITECTURE.md: System architecture (§5.0 InvariantMonitor, §6.2 Checkpointing, §9.0 Observability)
- docs/OBSERVABILITY.md: LangSmith integration details

### Deferred ADRs (Related Concepts)
- ADR-MCP-002: The Dockyard — Off-graph file storage (file_registry pattern, DockmasterSpecialist)
  - Partially implemented via ManifestManager (branches), missing file uploads

### Early Blueprints (Historical Context)
- 01_BLUEPRINTS/DESIGN_ The Emergent State Machine (ESM).md: Original LLM-driven state transition concept
- 01_BLUEPRINTS/ROADMAP_ Project RECESS: Original Hydrate/Execute/Dehydrate proposal
- DEEP_RESEARCH_CONVENING_DIALECTIC.md: Cross-pattern analysis (reconciled in ADR-CORE-031)

### External References
- [LLMs as Operating Systems](https://www.youtube.com/watch?v=52YtV_s8eXQ): LLMs as kernel managing resources/processes (parallels cognate mapping)
