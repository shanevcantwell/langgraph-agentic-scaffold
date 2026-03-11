# Deep Research ↔ Convening Dialectic

**Date:** 2025-12-03
**Context:** Exploring mutual influence between focused investigation (Deep Research) and persistent multi-model collaboration (Convening/HEAP)

---

## The Two Architectures

| Aspect | Deep Research | Convening/HEAP |
|--------|---------------|----------------|
| **Purpose** | Focused, single-purpose investigation | Sustained multi-model collaboration |
| **Duration** | Single session or short pipeline | Multi-session, persistent |
| **Memory** | Artifacts in GraphState | Filesystem Manifest (Heap) |
| **Agents** | Specialized primitives (WebSpecialist) | Heterogeneous pool with affinity routing |
| **Orchestration** | SystemsArchitect → PlanExecutor | TribeConductor (CPU metaphor) |
| **State** | SystemPlan with steps | Branches with status/phase |

---

## Part 1: How Convening Informs Deep Research

### 1.1 The Heap/Stack Metaphor Applied to Research

**Current Deep Research gap:** The Dialectic says "Artifacts hold the state" but doesn't address multi-session investigations.

**Convening insight:** The context window is execution memory (Stack), not storage. Research findings should persist to Heap.

**Application to Deep Research:**
```
Research Session 1:
  User: "What are the best CRM options for startups?"
  → Search: 10 results found
  → Browse: 3 articles read
  → Extract: Pricing data collected
  → Session ends, state lost ❌

With HEAP:
  → Manifest.json tracks research_branch
  → context_snippet: "Found HubSpot, Salesforce, Pipedrive. Pricing extracted."
  → Next session cold-starts from snippet ✓
```

**Proposed Integration:**
- `ResearchManifest` extends `ProjectManifest` for investigation-specific tracking
- Research topics as branches with `INVESTIGATION`, `VALIDATION`, `SYNTHESIS_READY` phases
- Search results, browsed pages, extracted data stored in branch documents

### 1.2 Branch Structure for Research Threads

**Current Deep Research gap:** Linear pipeline (Search → Browse → Extract → Summarize) doesn't capture parallel investigation threads.

**Convening insight:** Branches model parallel work streams with dependencies.

**Application to Deep Research:**
```
trunk.md: "User wants CRM comparison for startup"
├── branch-hubspot.md (search + browse results)
├── branch-salesforce.md (search + browse results)
├── branch-pipedrive.md (search + browse results)
└── synthesis triggered when all converge
```

**Proposed Integration:**
- `ResearchBranch` extends `BranchPointer` with research-specific metadata:
  - `search_query`: What was searched
  - `results_count`: How many results found
  - `urls_browsed`: Which pages were visited
  - `data_extracted`: Structured findings

### 1.3 Conflict Tracking for Contradictory Findings

**Current Deep Research gap:** When search results contradict, there's no structured way to capture the disagreement.

**Convening insight:** `Conflict` model explicitly tracks agent disagreements for forensic analysis.

**Application to Deep Research:**
```python
Conflict(
    branches=["branch-hubspot", "branch-g2crowd"],
    agent_a="web_specialist",
    position_a="HubSpot free tier supports 1,000 contacts",
    agent_b="data_extractor",
    position_b="HubSpot pricing page says 500 contacts",
    resolution=None,  # Flagged for clarification
)
```

**Proposed Integration:**
- When DataExtractor finds contradictory data across sources, record as `Conflict`
- Trigger HitL clarification (`clarification_required`) for user to resolve
- Synthesis agent must address open conflicts before completing

### 1.4 Semantic Firewall for Search Results

**Current Deep Research gap:** Search results could contain adversarial content or hallucination-inducing patterns.

**Convening insight:** The Semantic Firewall sanitizes data moving between Heap and Stack.

**Application to Deep Research:**
- **Read path:** Before loading search results into Synthesizer context, filter for injection patterns
- **Write path:** Before storing extracted data, validate against schema and strip low-entropy tokens

---

## Part 2: How Deep Research Informs Convening

### 2.1 The "Dumb Tool" Pattern

**Convening gap:** Agents in the pool (Alpha, Bravo, Research) are full specialists with prompts and reasoning.

**Deep Research insight:** WebSpecialist should be a "dumb tool" - no LLM, just API calls. The judgment happens elsewhere.

**Application to Convening:**
- Not all nodes in `build_convening_graph()` need to be full LLM agents
- Some could be pure tool nodes (file operations, API calls)
- Reduces cost and latency for deterministic operations

**Proposed refinement:**
```python
# In agent_router.py
class AgentProfile:
    ...
    is_tool_node: bool = False  # True = no LLM, just function execution
```

### 2.2 InferenceSpecialist as Affinity Type

**Convening gap:** `AgentAffinity` enum has ARCHITECTURE, IMPLEMENTATION, RESEARCH, MONITORING. But no "pure reasoning" option.

**Deep Research insight:** InferenceSpecialist (ADR-CORE-020) is the "just think" node - no tools, minimal prompt.

**Application to Convening:**
```python
class AgentAffinity(str, Enum):
    ARCHITECTURE = "architecture"
    IMPLEMENTATION = "implementation"
    RESEARCH = "research"
    MONITORING = "monitoring"
    INFERENCE = "inference"  # NEW: Pure semantic judgment
    DEFAULT = "default"
```

**Use cases in Convening:**
- Branch relevance judgment ("Is this branch still needed?")
- Conflict interpretation ("Are these positions actually contradictory?")
- Synthesis readiness ("Have we gathered enough to synthesize?")

### 2.3 The RECESS Controller Pattern

**Convening gap:** The TribeConductor is described but the worker-to-worker isolation isn't explicitly enforced.

**Deep Research insight (via RECESS):** Workers don't know about each other. The Controller knows about workers. No hard edges between workers.

**Application to Convening:**
- Progenitor Alpha should NOT know Progenitor Bravo exists
- Alpha returns to Conductor, Conductor decides to invoke Bravo
- Prevents the coupling error Gemini made (WebSpecialist → PlanExecutor hard edge)

**Verification question:** In `build_convening_graph()`, all agent nodes return to conductor:
```python
for node in ["progenitor_alpha", "progenitor_bravo", ...]:
    graph.add_edge(node, "conductor")
```
✓ This is correct. No direct agent-to-agent edges.

### 2.4 The Reasonable Agent Test

**Convening gap:** Everything goes through LLM agents. But is that always justified?

**Deep Research insight:** "Is implementing [X] as agentic behavior preferable to a couple bespoke scripts?"

**Application to Convening:**
| Convening Operation | Agentic? | Reasoning |
|---------------------|----------|-----------|
| TribeConductor routing | Yes | Requires judgment about branch priority |
| Agent work on branch | Yes | Core reasoning task |
| Manifest I/O | **No** | Deterministic file operations |
| Context snippet generation | Maybe | Could be LLM (summary) or heuristic (first N chars) |
| Hash chain computation | **No** | Pure function |
| Path validation | **No** | Regex/pathlib operation |

### 2.5 HitL Clarification Integration

**Convening gap:** `human_intervention` node exists but the structural guarantee of HitL isn't explicit.

**Deep Research insight:** ADR-CORE-018's `clarification_required` status provides code-enforced pause, not prompt-level hope.

**Application to Convening:**
```python
class BranchStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    STALE = "stale"
    CONVERGED = "converged"
    COMPLETE = "complete"
    ABANDONED = "abandoned"
    CLARIFICATION_REQUIRED = "clarification_required"  # NEW: HitL pause
```

**Integration with ADR-CORE-018:**
- When Conductor detects `CLARIFICATION_REQUIRED`, route to DialogueSpecialist
- Graph checkpoints via PostgresSaver
- Resume from exact state after user responds

---

## Part 3: Unified Architecture Questions

### 3.1 Two Persistence Layers?

**Tension:** Deep Research could use Convening's HEAP, but Convening also proposes PostgreSQL for checkpointing (ADR-CORE-018).

**Resolution options:**
1. **HEAP for content, PostgreSQL for graph state** - Manifest tracks research findings, checkpointer tracks execution state
2. **HEAP only** - File-based checkpointing (simpler, but less robust)
3. **PostgreSQL only** - Store manifest as JSONB column (more complex, but unified)

**Recommendation:** Option 1. HEAP handles the "what" (content, findings, conflicts). PostgreSQL handles the "where" (graph state, execution position).

### 3.2 Research as Convening Subgraph?

**Question:** Should Deep Research be implemented AS a Convening subgraph, or as a separate capability?

**Arguments for subgraph:**
- Inherits persistence (HEAP), conflict tracking, forensic logging
- Research branches naturally map to investigation threads
- TribeConductor can route to research agents

**Arguments for separate:**
- Deep Research is simpler (focused investigation vs. sustained collaboration)
- Convening's multi-agent pool may be overkill for "search and summarize"
- Faster iteration on Deep Research without Convening dependencies

**Recommendation:** Build Deep Research Phase 1 (WebSpecialist primitive) separately. In Phase 2, evaluate whether to integrate with Convening or keep independent.

### 3.3 InferenceSpecialist Placement

**Question:** Where does InferenceSpecialist live?

**Options:**
1. **MCP Service** - Callable by any specialist synchronously
2. **Graph Node** - Routable by Conductor like other agents
3. **Built into Conductor** - Conductor's own judgment capability

**Recommendation:** Option 1 (MCP Service). This allows:
- Any specialist to call `inference_specialist.judge()` for quick judgment
- Conductor to use it for routing decisions
- No graph routing overhead for simple judgments

---

## Questions for Cross-Document Resolution

### For Deep Research (Gemini):
1. Should research findings persist to HEAP between sessions?
2. Should search result branches use Convening's `BranchPointer` structure?
3. How should contradictory findings be tracked - as `Conflict` records?

### For Convening (Implementation):
1. Should `AgentAffinity` include `INFERENCE` for pure semantic judgment?
2. Should `BranchStatus` include `CLARIFICATION_REQUIRED` for HitL integration?
3. Should some agent nodes be "tool nodes" (no LLM, just function execution)?

### For Both:
1. What is the relationship between HEAP (filesystem manifest) and PostgreSQL checkpointing?
2. Should research capability be a Convening subgraph or independent?
3. Where does InferenceSpecialist (ADR-CORE-020) fit in the unified architecture?

---

## Summary

The Deep Research and Convening architectures are **complementary**:

- **Convening provides** persistence, conflict tracking, forensic logging, and the Heap/Stack metaphor
- **Deep Research provides** the "dumb tool" pattern, Reasonable Agent Test, and focused investigation primitives

A unified architecture would:
1. Use HEAP for content persistence (research findings, branch documents)
2. Use PostgreSQL for graph state checkpointing (HitL pause/resume)
3. Apply the RECESS Controller pattern to both (workers isolated, controller orchestrates)
4. Include InferenceSpecialist as MCP service for pure semantic judgment
5. Integrate HitL clarification as `CLARIFICATION_REQUIRED` status

The key insight from both: **Not everything needs to be agentic.** The Reasonable Agent Test applies to Convening's operations just as much as to Deep Research's primitives.

---

## Resolution: ADR-CORE-031 (Iterative Reasoning Pattern)

The overlap between Deep Research and Convening has been formally reconciled in **ADR-CORE-031: Iterative Reasoning Pattern**.

**Key reconciliation points:**

1. **Convening owns POLICY** (when, why, who) — TribeConductor, AgentRouter, Heap persistence
2. **IRP owns MECHANISM** (how) — Generate → Compress → Evaluate loop
3. **Fishbowl (023) IS an IRP instance** — not a separate implementation
4. **Context snippets (023) = Summarization Gates (031)** — same concept, one implementation

See ADR-CORE-031, section "Relationship to ADR-CORE-023 (Convening of the Tribes)" for implementation guidance.
