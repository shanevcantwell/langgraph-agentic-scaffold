# PROPOSAL: Eval Architecture and Sleeptime Subgraph

**Status:** Discussion Draft (Feb 2026)
**Context:** Session artifacts from Phase 1 completion through Phase 3 design
**Purpose:** Capture architectural decisions and open questions for cross-model discussion (Opus conversation_search, Gemini 3.0 insight)

---

## 1. What We Settled

### 1.1 Two Containers, Two Purposes

prompt-prix ships as **two distinct containers** from the same Docker image:

| Container | Entry Point | Purpose | Consumer |
|-----------|-------------|---------|----------|
| `prompt-prix-mcp` | `prompt-prix-mcp` (stdio MCP server) | Stateless iteration primitives | LAS specialists via `sync_call_external_mcp()` |
| `prompt-prix` | `prompt-prix-cli` / `prompt-prix` (Gradio) | Full application: batteries, UI, CLI | LAS via `docker exec`, humans via browser/terminal |

**The distinction matters because:**
- The MCP server is lightweight, stateless, iteration-level. It exposes `react_step`, `complete`, `list_models`. These are primitives for LAS specialist integration (eventually replacing ReActMixin).
- The full app container runs battery evaluations, manages adapter pools, handles concurrent multi-model dispatch. `run-battery` needs the complete application context — pool lifecycle, adapter registry, result aggregation. This is not MCP-shaped work.

**Battery runs go through the CLI, not MCP.** There is no `run_battery` MCP tool. LAS invokes batteries via an internal MCP tool that shells out to `docker exec prompt-prix prompt-prix-cli run-battery --config ...`.

### 1.2 Model Agnosticism Through Container Walls

The eval workflow must not be coupled to any specific adapter or backend. Batteries should run against:
- Local models via LM Studio (PooledLMStudioAdapter, current)
- Local models via future Ollama adapter
- Frontier models via surf-mcp (browser automation to Claude/ChatGPT/Gemini UIs)
- Frontier models via API adapters (Anthropic SDK, OpenAI SDK, Together)

**prompt-prix owns adapter routing internally.** LAS never imports from prompt-prix, never touches its adapter stack. The container wall is the boundary. LAS says "run this battery" and gets results back. Which models, which adapters, which GPUs — all prompt-prix's problem.

### 1.3 The Internal MCP Tool Pattern

From LAS's perspective, calling prompt-prix for batteries is an **internal MCP tool** registered in LAS's MCP registry:

```python
# Registered in LAS internal MCP
class PromptPrixBatteryTool:
    """Internal MCP tool that wraps docker exec to prompt-prix CLI."""

    def run_battery(self, config: dict) -> dict:
        # 1. Write config to shared volume or temp file
        # 2. docker exec prompt-prix prompt-prix-cli run-battery --config /path
        # 3. Parse results from stdout/file
        # 4. Return structured results
        ...
```

Specialists call it like any other internal MCP tool. The docker exec mechanics are hidden behind the interface. Same pattern as existing internal MCP services, just happens to shell out to a container.

### 1.4 ReActMixin: Accepted Debt, Not Strategic Direction

Phase 1b spread ReActMixin to `text_analysis_specialist` — accepted as tactical debt. The strategic direction remains:

- **Phase 2b:** Build prompt-prix MCP server (`react_step`, `complete`, `list_models`)
- **Phase 5:** Migrate LAS ReActMixin consumers to `react_step()` MCP (tool-forwarding mode)
- **End state:** ReActMixin shrinks from ~500 lines to ~50 lines of thin orchestration

The tool-forwarding pattern (Option A from the react_step investigation):
1. LAS calls `react_step()` via MCP — prompt-prix handles inference, parsing, schema building
2. react_step returns pending tool calls (no mock dispatch)
3. LAS executes tools locally (where MCP services live)
4. LAS calls react_step again with updated trace
5. Loop until completed

This requires a ~20-line change in prompt-prix: when `mock_tools={}`, return `pending_tool_calls` instead of raising `ReactLoopIncomplete`. Backward-compatible — eval mode (mock_tools populated) is untouched.

**Not building this yet.** Eval (Phase 3) validates the trace format and iteration semantics first. Migration happens after.

---

## 2. What We Haven't Settled

### 2.1 Who Owns the Eval Workflow?

The eval workflow is **not user-facing**. Nobody types "evaluate my models" into the chat interface. It's background work. This raises the question: who orchestrates it?

**Options discussed:**

**A. Standalone script (Phase 3 minimum)**
```bash
docker exec langgraph-app python -m app.src.eval.run_battery --config battery.yaml
```
Simplest possible. Proves integration end-to-end. No graph involvement. But doesn't use any LAS infrastructure — no state management, no archival, no artifact flow.

**B. Specialist in the main graph**
A specialist that can be routed to by the main graph. User could say "evaluate the PD prompt against 3 models" and it would run. But eval is inherently long-running (minutes to hours for full batteries) — it doesn't fit the request-response pattern of the main graph.

**C. Sleeptime subgraph**
A separate graph that runs independently of the main conversation flow. Triggered by idle time, schedule, or explicit invocation. This is the ADR-066 vision.

### 2.2 The Sleeptime Subgraph Question

The eval workflow is the first concrete use case for sleeptime compute. The architectural questions:

**What triggers it?**
- Idle time detection (no user requests for N minutes)?
- Schedule (cron-like: "run overnight")?
- Explicit invocation ("run tournament now")?
- Event-driven ("prompt file changed in last commit")?

**What's the subgraph shape?**

```
SleeptimeOrchestrator (SO)
  Decides what background work to do
  Manages priorities across eval, consolidation, memory maintenance
    |
    v
ModelTournament specialist
  Runs batteries for a specific specialist role
  Calls internal MCP tool (docker exec prompt-prix CLI)
  Scores results via calculate_drift (semantic-chunker MCP)
  Produces ranking artifacts
    |
    v
ArchiveTestExtractor (Phase 4)
  Mines successful archives for new test cases
  Feeds extracted tests back into tournament corpus
```

**Is the SO too high-level for Phase 3?** Probably. The SO is Phase 6 territory — it needs to reason about what's stale, what's changed, what to prioritize. That's a scheduling problem layered on top of eval.

**Minimum viable subgraph for Phase 3:**
- No SO (hardcoded trigger: explicit invocation)
- Single specialist: runs battery, scores results, writes artifacts
- Shared state with main graph only through artifacts (artifact heap is cross-specialist)
- Archive serialization for results (same archiver as main graph)

### 2.3 Scoring Architecture

Two scoring mechanisms exist:

**Semantic drift** (`calculate_drift` via semantic-chunker MCP):
- Cosine distance in NV-Embed-v2 4096-dim space
- Calibrated: correct file categorizations land at ~0.25-0.28 drift
- 0.3 = "semantic squelch" threshold for behavioral correctness
- Good for: "did the model produce a response semantically close to the exemplar?"

**Structural validators** (from TROUBLESHOOTING.md patterns, Phase 4):
- `ReasoningActionsConsistencyValidator` — reasoning matches the action taken
- `ReadToMoveTransitionValidator` — PD reads files before attempting moves
- `DestinationIncludesFilenameValidator` — move destinations include the filename
- Good for: "did the model follow the correct behavioral pattern?"

**Open question:** Where does scoring live? Options:
- In LAS (specialist calls `calculate_drift` via semantic-chunker MCP, runs structural validators locally)
- In prompt-prix (CLI output includes drift scores — prompt-prix already has semantic-chunker access)
- Split: prompt-prix handles drift (it has the adapter), LAS handles structural validators (it has the domain knowledge)

### 2.4 Test Case Format and Flow

**Current format** (hand-written YAML in `docs/tests/promptfoo/`):
```yaml
- description: "PD categorizes 6 files correctly"
  vars:
    user_request: "Organize these files into categories..."
    gathered_context: "workspace/categorize_test/ contains: 1.txt, 2.txt..."
    pass_criteria: "Creates correct directories and moves files"
    expected_response: "I've organized the files into..."
```

**How does this flow through the system?**

1. LAS specialist reads YAML from filesystem (or receives in artifacts)
2. Formats as prompt-prix battery config
3. Calls internal MCP tool → docker exec → prompt-prix CLI
4. prompt-prix runs battery: N test cases x M models x K seeds
5. Results come back as structured JSON
6. LAS specialist scores via `calculate_drift` and/or structural validators
7. Results written to `artifacts["eval_results"]`
8. Archived alongside normal workflow artifacts

**Open question:** Should prompt-prix own the YAML format? Or should LAS own the test case schema and translate to prompt-prix's battery config format? The test cases contain LAS-specific concepts (specialist roles, tool expectations, structural assertions) that prompt-prix doesn't need to understand.

### 2.5 Where Does Archive Extraction Live?

Phase 4's `ArchiveTestExtractor` mines `logs/archive/*.zip` for successful runs and extracts test cases. This is LAS domain logic — it understands archive structure, specialist roles, trace formats.

But the extracted test cases need to flow to prompt-prix for battery execution. So:

```
LAS (extraction) → test artifacts → LAS (formatting) → prompt-prix (execution) → LAS (scoring)
```

The extraction is clearly LAS-side. The question is whether it's a specialist, a script, or a sleeptime task.

---

## 3. Architectural Principles Reinforced

### 3.1 Context Firewalls

Repo boundaries and Docker images are **memory protection rings** against context-window damage. prompt-prix, local-inference-pool, semantic-chunker are separate repos specifically so AI assistants can't accidentally grow or damage code when operating with incomplete context.

The 50k+ line LAS codebase is 100x anything the user has previously worked on. Encapsulation is a survival strategy, not an architectural luxury.

### 3.2 Container Wall = API Boundary

LAS talks to prompt-prix through exactly two interfaces:
- **MCP stdio** (prompt-prix-mcp container): `sync_call_external_mcp("prompt-prix", tool_name, args)`
- **docker exec CLI** (prompt-prix app container): `docker exec prompt-prix prompt-prix-cli ...`

No Python imports across the boundary. No shared state except files on shared volumes. `ModuleNotFoundError` is a harder wall than code review.

### 3.3 Procedural Everything Except Semantic Judgment

From ADR-068's primitives stack:
- Battery execution is **procedural** — run N tests, collect N results
- Adapter routing is **procedural** — least-loaded server, JIT-swap guard
- Drift scoring is **procedural** — cosine distance computation
- **Only semantic judgment** (deciding what to evaluate, interpreting results, prioritizing) requires LLM invocation

The SleeptimeOrchestrator (Phase 6) is the first component that genuinely needs to *reason* about what to do. Everything below it in the stack is deterministic.

---

## 4. Decision Points for Discussion

These are the questions that benefit from multi-model architectural discussion:

1. **Phase 3 shape:** Standalone script vs. specialist vs. minimal subgraph? What's the right balance between "prove it works" and "build it right"?

2. **Scoring ownership:** Should prompt-prix return drift scores (it has semantic-chunker), or should LAS score independently? Split scoring introduces coordination complexity but preserves separation of concerns.

3. **Test case schema ownership:** LAS-specific concepts (specialist roles, structural assertions) don't belong in prompt-prix. But prompt-prix needs to understand test case format to run batteries. Where's the translation layer?

4. **Sleeptime trigger design:** Event-driven (prompt changed) vs. scheduled (overnight) vs. explicit (user command) vs. idle-detected? These have very different infrastructure requirements.

5. **Subgraph isolation:** How much state does the eval subgraph share with the main conversation graph? Artifacts only? Messages too? Separate archiver? The isolation boundary determines how much infrastructure we need.

6. **The SO's intelligence level:** Is the SleeptimeOrchestrator an LLM-powered scheduler (decides what to evaluate based on what changed) or a rule-based scheduler (runs batteries on a fixed schedule)? The former is Phase 6 ambition; the latter is achievable in Phase 3.

---

## 5. Concrete Next Steps (Ordered by Dependency)

### Immediately Actionable (No Blockers)

1. **Internal MCP tool for battery execution** — Register in LAS MCP registry. Wraps `docker exec prompt-prix prompt-prix-cli run-battery`. Proves the integration path.

2. **Battery config translation** — Map LAS test case YAML to prompt-prix battery config format. Understand what prompt-prix needs vs. what LAS adds.

3. **Phase 2b: prompt-prix MCP server** — Thin wrapper exposing `react_step`, `complete`, `list_models`. Same codebase as CLI, different entry point. (Sibling repo work.)

### Requires Design Decision

4. **Eval specialist or subgraph** — Depends on decision point #1 above. The internal MCP tool works either way; the question is who calls it.

5. **Scoring pipeline** — Depends on decision point #2. Can start with LAS-side scoring only (specialist calls `calculate_drift` after battery results return).

### Future (Phase 4+)

6. **ArchiveTestExtractor** — Mines archives for test cases. Requires archive format stability guarantee.

7. **SleeptimeOrchestrator** — Scheduling layer. Requires eval to be proven first.

8. **ReActMixin migration** — Depends on Phase 2b (MCP server) + eval validation of trace format.

---

## Appendix: Key References

- **ADR-CORE-056** — Model Tournament vision (specialist profiles, archive extraction, semantic validators)
- **ADR-CORE-064** — Prompt-Prix MCP Integration
- **ADR-CORE-066** — Sleeptime Autonomous Orchestration
- **ADR-CORE-068** — Shared GPU Pool Extraction
- **prompt-prix CLI** — `prompt-prix-cli models`, `prompt-prix-cli run-battery` (implemented, container running)
- **react_step()** — `prompt_prix/mcp/tools/react_step.py` (stateless single-iteration primitive)
- **ReActMixin** — `app/src/specialists/mixins/react_mixin.py` (~500 lines, marked for deprecation)
- **Drift calibration** — Correct categorizations at ~0.25-0.28 drift in NV-Embed-v2 space. 0.3 = semantic squelch threshold.
