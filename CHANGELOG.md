# Changelog

## Alpha 2 (2026-03-11)

**891 commits | 262 issues tracked (112 closed) | Aug 2025 – Mar 2026**

---

### Architecture & Orchestration

**Specialist Routing & Graph Flow**
- **Hub-and-spoke orchestration** with turn-by-turn Router decisions. Router acts as CPU/scheduler — every routing decision is observable and auditable.
- **Three-stage pipeline**: Triage (gate) → SystemsArchitect (plan) → Specialist (execute). Triage was flipped ahead of SA (#199) so cheap classification gates expensive planning.
- **Signal-based completion** (#225): Specialists write `completion_signal` artifacts. Exit Interview reads them as fast-path — 0ms evaluation for clean exits.
- **Three chat modes**: CORE-CHAT-001 (single specialist), CORE-CHAT-002 (parallel progenitors + synthesis), CORE-CHAT-003 (diplomatic arbiter loop for high-stakes).
- **Deterministic greeting gate** in Router (#208, #210) — greetings skip the full planning pipeline.

**delegate() — Recursive Invocation**
- **Implemented** (ADR-045, #201, #202): Context-isolated subtask invocation with own lifecycle. Direct `graph.invoke()`, not HTTP round-trip.
- **Cascade cancellation** (#203): Parent cancellation propagates to all child invocations.
- **Error context propagation** (#204): Child failures bubble structured error back to parent.
- **Renamed from fork() to delegate()** (#225) for better alignment with model training data.

**Signal Processor (ADR-077)**
- **SignalProcessorSpecialist** (#200): Dedicated node for evaluating state signals with replace reducer semantics. Decouples signal interpretation from specialist execution.

**Safety & Governance**
- **SafeExecutor** wraps all specialist execution — no specialist can terminate the graph, corrupt state, or bypass safety constraints.
- **Defense against WGE** (Whispering Gallery Effect): Context curation at specialist boundaries, explicit state management.
- **Multi-model adversarial validation**: Different providers for ProgenitorAlpha vs ProgenitorBravo catch correlated errors.
- **Four-stage termination**: Specialist → Signal Processor → Exit Interview → End/Archiver. No unilateral exits.

---

### LLM Adapter Layer

**Multi-Provider Architecture**
- **Provider type taxonomy**: `local`, `local_pool`, `llama_server`, `llama_server_pool`, `gemini`.
- **LocalInferenceAdapter base class** extracted — shared protocol fixups applied unconditionally.
- **LlamaServerAdapter** (#253): Dedicated adapter for llama-server with thread-safe connection pooling.
- **ServerQuirks eliminated** (#260): Harmony token stripping, $ref/$defs inlining, and empty content handling are unconditionally safe — the entire quirk dispatch system was unnecessary and removed.

**Pooled Inference**
- **GPU pool adapter** (ADR-068, #141): Consumes local-inference-pool for multi-GPU dispatch.
- **Per-server authentication** (#235): Token passthrough for authenticated inference endpoints.
- **Server health feedback** (#237): `report_server_error` propagates failures back to pool for routing decisions.

**Schema & Grammar Fixes**
- **$ref/$defs inlining** (#260): Pydantic schemas with references are flattened before sending to grammar engine.
- **Thinking suppression** (#261): Per-request `thinking: false` for grammar-constrained calls prevents reasoning tokens from corrupting structured output.
- **Grammar recovery** (#255, #258): Code-fence-wrapped JSON extracted before grammar rejection.
- **Harmony token stripping** (#218): LM Studio's `<|harmony|>` prefix tokens cleaned from responses.
- **Structured output validation** (#123): Moved from specialist-level to adapter-level for consistent enforcement.

---

### Specialist Ecosystem

**ProjectDirector (PD) — Autonomous ReAct Agent**
- **Holistic prompt rewrite** (#214): Removed redundancy and model-confusing content.
- **Tool refresh** (#225): `delegate()`, `summarize()`, `write_artifact()` added; stale research tools removed.
- **DONE schema** (#232): Explicit completion schema for prompt-prix interception.
- **webfetch-mcp integration** (#220, #221): Replaced built-in search/browse with MCP web tools.
- **Ghost artifact prevention** (1aa6b8e): Empty `write_artifact` calls rejected.
- **Stagnation detection** (9b6fe3c): Reads STAGNATION sentinel instead of repeated tool calls.
- **read_file size gate** (#244): Large files trigger delegation instead of context flooding.

**Exit Interview (EI) — Completion Verification**
- **Re-architected** (#195): Killed non-ReAct path, extracted artifact tools.
- **Artifact-presence fast-path** (#243): Spoke specialists skip full evaluation when artifacts exist.
- **react_step-only verification** (#195, #196): Config-driven max_iterations.
- **Outcome verification** (#173): Evaluates observable outcomes, not process traces.

**SystemsArchitect (SA)**
- **Acceptance criteria** (#173, #216): Schema validator with fail-fast on empty/missing criteria.
- **exit_plan scoped to caller's tools** (#131).
- **Conditional edge** (#217): Missing task_plan triggers fail-fast instead of silent propagation.

**Triage**
- **Reject-with-cause** (#179): Underspecified prompts get explicit rejection.
- **ACCEPT/REJECT classifier** (#197, #199): Binary gate before SA investment.
- **Context plan elimination** (e4d6ec5): Actions moved to scratchpad, reducing state bloat.

**Facilitator — ISO-9000 Context Assembly**
- **Accumulated work** + shared context helpers (80f7142).
- **RESEARCH action wired to webfetch-mcp** (#223).
- **EI feedback curation** (#167): Prevents stale feedback accumulation on retry.

**Removed Specialists**
- NavigatorSpecialist (#26), WebSpecialist, BrowseSpecialist, ResearchOrchestrator (#222) — replaced by MCP services.
- Critic subgraph (#160, #161) — EI + SA provide the quality gate.
- ReActMixin (#162) — PD and EI migrated to react_step() MCP.

---

### MCP Services

**Internal MCP**
- **Artifacts service** (#174): `list_artifacts()` and `browse_artifact(key)` for specialist access to shared state.
- **Config-level tool binding** (ADR-051, #57): MCP tools bound per-specialist in config.yaml.

**External MCP Ecosystem**
- **prompt-prix**: LLM interface + eval platform. Owns the model boundary via `react_step`.
- **webfetch-mcp**: Web search and page fetching.
- **surf-mcp**: Browser automation with Fara visual grounding.
- **semantic-chunker**: Embedding infrastructure (embeddinggemma-300m, NV-Embed-v2).
- **terminal-mcp**: Shell command execution (bash, not dash — #234).
- **it-tools-mcp**: 119 IT utility tools.

---

### UI & Observability

**V.E.G.A.S. Terminal**
- **State timeline snapshots** (#184): SSE-powered state inspection with snapshot paging.
- **Mission Report** (#181): Paging and artifact context selection.
- **Live intra-node progress** (8538b8c): Polling + delegate() observability breadcrumbs.
- **Conversation threading**: Prior messages merge (#245, #249).
- **html_document CSS isolation** (#263): HTML artifacts excluded from report and source display to prevent CSS leakage.

**Archive System**
- **Timestamped zip archives** per workflow run: manifest, llm_traces, final_state, artifacts.
- **Narrative report** (#175): Execution timeline with structured output.
- **State timeline in archive** (#184).

**OpenAI-Compatible API**
- **Chat endpoint** (6fd3017): Standard `/v1/chat/completions` interface exposes the full orchestration pipeline. Any OpenAI-compatible client (Continue, AnythingLLM, OpenAI SDK) can drive LAS directly.

---

### Developer Experience

**Installation**
- **Interactive installer** (`setup.sh` / `setup.ps1`): Detects environment, walks through provider selection, generates all config files.
- **Bare-bones installer** (`install.sh`): Copy examples and create venv for minimal setup.
- **LMSTUDIO_* → LOCAL_INFERENCE_* migration**: All env vars, scripts, and docs use canonical names.

**Configuration**
- **Three-tier system**: `.env` (secrets), `config.yaml` (committed blueprint), `user_settings.yaml` (local model bindings).
- **Provider-agnostic**: Any OpenAI-compatible server works. LM Studio, llama-server tested.
- **Distributed inference**: Multi-GPU via `LOCAL_INFERENCE_SERVERS` name=url format.

**Documentation**
- **40 specialist briefing docs** in `docs/specialists/`.
- **55+ ADRs** across completed, implemented, proposed, and subsumed categories.
- **README rewrite** for alpha 2: Explicit MoE framing, updated env vars, prerequisites, research directions extracted to `docs/RESEARCH.md`.

---

### State Management

- **GraphState with Annotated merge**: `artifacts` uses dict merge (`operator.ior`), `messages` uses append (`operator.add`). Prevents context collapse in parallel execution.
- **Dossier pattern**: State-mediated communication between specialists with metadata, content payload, and explicit handoff.
- **prior_messages merge** (#245, #249): Conversation history preserved across specialist boundaries.
- **final_user_response artifact** (#245): Explicit artifact for end-user-facing output.

---

### Bug Fixes (Selected)

| Issue | Description |
|-------|-------------|
| #119 | LMStudio adapter discards message.content when tool_calls present |
| #128 | Spurious 'catastrophic failure' on successful workflow completion |
| #135 | Harmony format degrades after ~10 tool calls |
| #136 | JSON schema missing required tool_name breaks Router |
| #142 | task_is_complete concurrent write crash in parallel progenitors |
| #144 | Ghost node causes KeyError crash |
| #145 | Docker socket permissions block all MCP services |
| #150 | EI receives tool-call args instead of CompletionEvaluation JSON |
| #154 | ContextPlan schema mismatch with Pydantic model |
| #159 | temperature/top_p not overriding LM Studio server defaults |
| #232 | PD missing DONE schema for prompt-prix interception |
| #234 | terminal-mcp brace expansion fails (dash vs bash) |
| #240 | PD hangs — prompt-prix-mcp entrypoint replaced with tail -f |
| #245 | EndSpecialist synthesis LLM call hangs 15min on trivial responses |
| #258 | Triage fallback AIMessage cascades into SA prefill error |
| #260 | output_model_class sends raw $ref/$defs to llama-server |
| #261 | Grammar error handler silently promotes 500 error payloads |
| #263 | html_document CSS leaks into report and artifact source display |
