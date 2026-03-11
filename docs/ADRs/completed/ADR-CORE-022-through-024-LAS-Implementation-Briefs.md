# LAS Cognitive Architecture: Implementation Briefs

**Purpose:** Sequential implementation guidance for coding assistants.  
**Order:** 022 → 023 → 024 (each builds on previous)

---

## Brief 1: ADR-CORE-022 — The Heap

### What It Is
Filesystem-backed persistence layer. Treats Context Window as Stack (fast, limited), Filesystem as Heap (slow, infinite). Stores pointers to content, never full content.

### Implement Now
```
app/src/specialists/schemas/_manifest.py
app/src/utils/manifest_manager.py
```

**Schemas:**
- `BranchStatus` enum: ACTIVE, BLOCKED, STALE, CONVERGED, CLARIFICATION_REQUIRED, COMPLETE, ABANDONED
- `BranchPhase` enum: INVESTIGATION, VALIDATION, SYNTHESIS_READY
- `AgentAffinity` enum: ARCHITECTURE, IMPLEMENTATION, RESEARCH, INFERENCE, MONITORING, DEFAULT
- `ContributionEntry`: Forensic log with hash chain (content_hash, previous_hash)
- `BranchPointer`: Header (id, filepath, affinity, status) + Payload (context_snippet, metadata)
- `ProjectManifest`: Allocation table (branches dict, contribution_log list)

**ManifestManager:**
- Atomic writes: `tempfile.NamedTemporaryFile` + `os.replace`
- Path confinement: Validate all paths stay within project root
- Hash chaining: Each contribution hashes previous entry
- CRUD: add_branch, update_status, update_snippet, log_contribution, get_by_status/affinity

**Key Constraints:**
- `metadata` keys must be namespaced (`research.query`, `project.name`) except reserved (`priority`, `source`, `tags`)
- All models use `extra='forbid'` — no hidden fields
- Context snippets ~500 words max

### Do NOT Implement
- TribeConductor (that's 023)
- Agent routing logic (that's 023)
- Research pipeline (that's 024)
- Any LLM calls — this is pure I/O infrastructure

### Forward-Thinking
- 023 will add `TribeConductor` that calls `dereference_branch()` and `commit_branch()` on this manager
- 024 will use `research.*` metadata namespace
- The `affinity` field drives routing in 023's `AgentRouter`

---

## Brief 2: ADR-CORE-023 — Convening of the Tribes

### What It Is
Multi-model orchestration policy layer. The "CPU" that routes work to agents, manages context switching, coordinates Fishbowl debates, triggers synthesis.

### Depends On
ADR-CORE-022 (The Heap) — must be implemented first.

### Implement Now
```
app/src/specialists/tribe_conductor.py
app/src/convening/agent_router.py
app/src/convening/semantic_firewall.py
app/src/workflow/convening_graph.py
```

**TribeConductor:**
- `execute_cycle(state)`: Main entry — if Fishbowl active, handle debate; else assess and route
- `dereference_branch(branch_id)`: Load context from Heap → Stack (apply firewall)
- `commit_branch(branch_id, content, agent_id)`: Store results Stack → Heap (apply firewall)
- `start_fishbowl(topic)` / `end_fishbowl()`: Synchronous Alpha/Bravo debate subroutine
- `trigger_synthesis(branch_ids)`: Merge converged branches

**AgentRouter:**
- Maps `AgentAffinity` → agent_id
- Default pool: progenitor_alpha (ARCHITECTURE), progenitor_bravo (IMPLEMENTATION/DEFAULT), inference_specialist (INFERENCE), research_specialist (RESEARCH), local_monitor (MONITORING)
- `route(affinity, prefer_fast, prefer_cheap)` → agent_id

**SemanticFirewall:**
- `sanitize_input(content)`: Strip injection patterns before loading to Stack
- `sanitize_output(content)`: Strip slop patterns before storing to Heap

**LangGraph Integration:**
- `ConveningState`: messages, manifest_path, active_branch_id, next_action, fishbowl_*, synthesis_pending, hitl_required
- Conditional routing: conductor → [alpha|bravo|inference|research|monitor|synthesis|human|end]
- All agents return to conductor (RECESS pattern: workers don't know about each other)

**Key Constraints:**
- Conductor is the ONLY component that loads/stores from Heap
- Fishbowl max 4 turns, detect circular arguments
- Apply Reasonable Agent Test: Manifest I/O, hash computation, path validation are NOT agentic

### Do NOT Implement
- Research pipeline (that's 024)
- Actual agent logic (just the routing and orchestration)
- Web search/browse tools (that's 024)

### Forward-Thinking
- 024 may invoke research as a subroutine or spawn separate workflow
- CLARIFICATION_REQUIRED status triggers HitL pause (integrates with ADR-CORE-018 checkpoints)
- Synthesis events will eventually need a dedicated synthesizer agent

---

## Brief 3: ADR-CORE-024 — Deep Research (STUB)

### What It Is
Focused investigation workflow: Search → Browse → Extract → Synthesize. Optimized for single-purpose research, not sustained collaboration.

### Depends On
- ADR-CORE-022 (The Heap) — for artifact persistence
- Optionally ADR-CORE-023 (Convening) — integration TBD

### Status: Draft — Requires Review

**Open Questions to Resolve:**
1. Should research persist to Heap between sessions? (Recommendation: Phase 1 no, Phase 2 yes)
2. Use `BranchPointer` or research-specific types? (Recommendation: Use BranchPointer with `affinity=RESEARCH`)
3. Where does InferenceSpecialist live? (Recommendation: MCP Service, callable by any specialist)
4. How does HitL integrate? (Recommendation: CLARIFICATION_REQUIRED status)

**Core Pattern: "Dumb Tool" Nodes**
- `WebSpecialist`: No LLM — just API calls (search, fetch, parse)
- `DataExtractor`: Hybrid — LLM for extraction, tool for storage
- `Synthesizer`: Full LLM for report generation
- `InferenceSpecialist`: Semantic judgment (relevance, quality)

**Research Metadata Namespace:**
```python
metadata = {
    "research.query": "...",
    "research.sources": [...],
    "research.results_count": N,
    "research.pages_browsed": N,
}
```

**Implementation Order:**
1. Phase 1: Standalone pipeline (no Heap integration)
2. Phase 2: Add Heap artifact storage
3. Phase 3: Evaluate Convening integration

### Do NOT Implement Until
- 022 and 023 are complete and tested
- Open questions above are resolved
- Claude Code reviews existing Deep Research implementation in codebase

---

## Dependency Summary

```
022 (Heap)        ← Implement first, pure infrastructure
    ↓
023 (Convening)   ← Implement second, uses 022's ManifestManager
    ↓
024 (Research)    ← Implement last, uses 022's Heap, may use 023's routing
```

## Key Interfaces Between Layers

**022 → 023:**
- `ManifestManager.add_branch()` / `get_branch()` / `update_*`
- `ManifestManager.log_contribution()` (hash-chained)
- `BranchPointer.affinity` drives `AgentRouter.route()`

**023 → 024 (Future):**
- Research may be a Convening branch with `affinity=RESEARCH`
- Or standalone workflow that commits artifacts via `ManifestManager`
- TribeConductor could spawn research as Fishbowl-style subroutine

## Security Checklist (All Layers)

- [ ] Atomic writes (tempfile + os.replace)
- [ ] Path confinement (no traversal outside project root)
- [ ] Hash chain integrity (verify_log_integrity)
- [ ] Namespace validation (metadata keys)
- [ ] Schema strictness (extra='forbid')
- [ ] Injection pattern filtering (SemanticFirewall)
