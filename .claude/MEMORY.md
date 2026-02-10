# LAS Project Memory

## BENIGN Continuation Context Loss (Feb 2026)

Root cause chain discovered for filesystem task failures on max_iterations:

1. **knowledge_base only tracks web research** (#120)
   - `_update_context_from_trace()` ignores read_file, create_directory, move_file
   - Fix: Add tracking for all filesystem operations

2. **Stale exit_interview feedback repeats** (#121)
   - Facilitator adds EI feedback on EVERY run, not just EI retries
   - Fix: Only add when `routing_history[-1] == "exit_interview_specialist"`

3. **Adapter may discard reasoning text** (#119)
   - LMStudio adapter drops `message.content` when tool_calls present
   - Fix: Include both, but don't rely on it (model-dependent)

**Key principle**: Track what the SYSTEM knows (tool results), not what the model explains. Tool calls and results are ground truth.

## Issue #115: SA as MCP Tool

- EI is graph-wired, can't use requires_artifacts
- Solution: EI calls SA via MCP on-demand for exit_plan
- Shared `_generate_plan()` avoids code duplication
- Implementation complete, tests written, pending commit

## Model Agnosticism

System must work with 20+ models (Gemini, Claude, local Qwen, etc). Fixes should:
- Not rely on specific model behaviors
- Capture system-observable state (tool results) over model-explained state
- Handle missing/empty fields gracefully

## Testing Notes

- Unit tests: `pytest app/tests/unit/ -v` (from host)
- Integration tests: `docker exec langgraph-app pytest -m integration` (requires Docker)
- Archives in `./logs/archive/*.zip` - authoritative ground truth

## Naming Conventions - CRITICAL

**ADR/doc filenames**: UPPERCASE prefix with underscores, Title-Case-Dashes for description:
- `ADR-CORE-055_Trace-Based-ReAct-Serialization.md`
- `PROPOSAL_Prompt-Prix-ReAct-Evaluation.md`
- NOT: `prompt-prix-react-eval.md` (lowercase dashes = wrong)

**Don't create new folders** without checking existing structure first:
- `docs/ADRs/` is a symlink to design-docs repo — ADRs go there via `docs/ADRs/proposed/`
- `docs/tests/promptfoo/` — eval YAMLs and results
- `docs/dev/` — dev guides
- `docs/proposals/` — cross-project proposals (new category as of Feb 2026)
- `scripts/` — standalone utility scripts (snake_case.py)

## Architectural Convergence Vision (Feb 2026)

### ADR-068: Pool Extraction + Service Boundary (subsumes ADR-067)

**Decision**: Extract `ServerPool`, `ConcurrentDispatcher`, `ServerConfig` (~280 lines) into standalone `local-inference-pool` package. Both prompt-prix and LAS import it as a declared dependency.

**Two consumption paths**:
- **Hot path (inference)**: LAS imports pool directly via `PooledLMStudioAdapter`. No MCP overhead.
- **Cold path (eval/analysis)**: LAS calls prompt-prix MCP tools (judge, react_step, drift). Existing `ExternalMcpClient`.

**Why not MCP-for-everything**: MCP stdio has no auth, no caller identity, single pipe. Acceptable for occasional eval calls, not for every specialist inference invocation.

**Accepted risk**: Two independent pools (LAS + prompt-prix) don't coordinate JIT-swap across consumers. Honest gap — fix requires shared pool process with IPC, not an additive change.

**Why not port (ADR-067's approach)**: Repo boundary = structural enforcement. `ModuleNotFoundError` is a harder wall than code review. Prevents AI assistants from blurring abstraction layers across sessions.

**Three-layer separation** (prompt-prix internal):
- Toolkit (complete, judge, etc.) → HostAdapter protocol → Adapters → Infrastructure (internal to LMStudioAdapter only)
- Pool is model-routing infrastructure, not request-handling. Doesn't know about InferenceTask or StandardizedLLMRequest.

### Primitives Stack

- **react_step** (procedural) — stateless single-iteration primitive from prompt-prix
- **parallel_dispatch** (procedural) — fan-out N requests, collect N responses
- **Deliberation patterns** (composed) — Fishbowl/Convening/Swimming as MCP tools, NOT graph topology

**Principle**: Procedural everything except semantic judgment. LLM invoked only for generating responses and evaluating completion.

ADRs: 066 (Sleeptime), 067 (subsumed), 068 (Pool Extraction), MCP-006 (Vision as MCP Tool)

## Sibling Repos

- **prompt-prix** — Gradio eval UI, LMStudio parallel fan-out, consistency runs
  - Has `expected_response` field (embedding anchor for `calculate_drift`)
  - Has `pass_criteria` field (rubric text for LLM judges)
  - **ReAct primitives**: `react_step()`, `build_react_messages()`, `detect_cycle_with_pattern()`
  - **CLI done**: `prompt-prix-cli models`, `prompt-prix-cli run-battery` — batch interface for agents
  - **NO MCP server yet** — MCP server is Phase 2b target for ReActMixin encapsulation
  - **Lineage**: LAS built ReActMixin → prompt-prix stole it → wrapped as stateless react_step() → LAS consumes back via MCP, sheds ~500 lines
- **local-inference-pool** v0.1.0 — extracted GPU pool infra (~280 lines, httpx + pydantic)
  - `ServerPool` (atomic slot management, JIT-swap guard, least-loaded balancing)
  - `ConcurrentDispatcher` (FIFO queue, head-of-line avoidance)
  - Already consumed by LAS via `PooledLMStudioAdapter`
- **semantic-chunker** — NV-Embed-v2 embeddings, already mounted as MCP in LAS
  - `calculate_drift` — cosine distance between texts
  - `classify_document` — DMA-mode classification
  - `analyze_variants` — prompt geometry in 4096-dim space
- **it-tools-mcp** — 119 IT utility tools (wrenchpilot/it-tools-mcp:v5.10.2). Committed, wired to text_analysis_specialist.

## Specialist Consolidation (Feb 2026) — DONE

`text_analysis_specialist` absorbed `data_extractor_specialist` and `data_processor_specialist` (commit `0c121ce`).
- Two execution modes: single-pass (fast path) and ReAct (when tools available)
- Tool belt: filesystem, terminal, semantic-chunker, it-tools MCP
- data_extractor/data_processor source files kept with deprecation notices, removed from config.yaml routing
- PD identity cleanup tracked in issue #151

## Eval Uses Pool Directly (No prompt-prix Blocker)

All four eval legs exist in LAS today:
- Read test data → filesystem MCP
- Parse structured data → terminal / it-tools MCP
- Call model → `PooledLMStudioAdapter.invoke()` (pool handles GPU routing)
- Compare to exemplar → `calculate_drift()` via semantic-chunker MCP

prompt-prix MCP needed for **encapsulation** (ReActMixin → container), not for eval capability.

## Key Files

- `facilitator_specialist.py` - context assembly, EI feedback surfacing
- `project_director.py` - filesystem ReAct loops, knowledge_base tracking
- `lmstudio_adapter.py` - tool call parsing, response format, `_build_request_kwargs`/`_parse_completion`
- `pooled_adapter.py` - PooledLMStudioAdapter, pool slot acquire/release
- `react_mixin.py` - trace-based serialization, thought capture (marked for deprecation → react_step MCP)
- `factory.py` - AdapterFactory, pool lifecycle, manifest refresh
- `state.py` - GraphState definition, reducers, artifacts: Annotated[Dict, operator.ior]
