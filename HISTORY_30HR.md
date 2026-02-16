# LAS 30-Hour History (Feb 15-16, 2026)

Generated: 2026-02-16T22:00 MST
Branch: development/testing

---

## Commits (chronological, oldest first)

### cf9e530 — 2026-02-15 13:26 — fix(facilitator,router,ei): BENIGN context surfacing, Router prompt restructure, truncation removal

Facilitator BENIGN early return now surfaces specialist_activity, task_plan, and EI feedback into gathered_context so Router has context for correct routing on retry paths.

Router dynamic prompt restructured: specialist list at top, gathered_context in middle (labeled as reference data), routing examples at bottom — addresses "lost in the middle" attention pattern that caused consistent WebBuilder misrouting for filesystem tasks.

Removed truncation violations in execution path (#183): Router gathered_context[:1500], EI _preview_artifact_value(max_len=300), exit_plan[:2000], steps[:10].

**Files:** facilitator_specialist.py, router_specialist.py, exit_interview_specialist.py, test_exit_interview_specialist.py, test_facilitator_benign.py

---

### bde7048 — 2026-02-15 13:45 — feat(observability): state timeline snapshots via SSE and archive (#184)

Add per-specialist state snapshots emitted as STATE_SNAPSHOT SSE events and persisted as state_timeline.jsonl in archives. Captures full state, prompts, IM decisions, and react traces at each specialist boundary.

Motivated by resume_trace saga: observability data must NOT live in state that models consume. state_timeline is write-only (like llm_traces).

**Files:** api.py, state.py, ag_ui_schema.py, translator.py, archiver_specialist.py, project_director.py, router_specialist.py, text_analysis_specialist.py, state_serializer.py, node_executor.py, graph_orchestrator.py

---

### c20b4fc — 2026-02-15 16:28 — docs: update specialist profiles for context_plan and resume_trace elimination

Removed stale requires_artifacts: ["context_plan"] from config.yaml. Removed dead recommended_specialists salvage in triage_architect.py. Updated FACILITATOR.md and PROJECT_DIRECTOR.md for resume_trace → specialist_activity. Fixed stale test assertions.

**Files:** triage_architect.py, test_file_sort.py, test_specialist_execution.py, test_facilitator_retry.py, test_thought_stream_events.py, config.yaml, TEST_SUITE_SUMMARY.md, FACILITATOR.md, PROJECT_DIRECTOR.md

---

### c457d6f — 2026-02-15 17:12 — feat(schema): add acceptance_criteria to SystemPlan (#173)

Root cause of EI verification loops: SystemPlan had no "what good looks like." EI generated exit_plan from user_request alone, SA invented unverifiable process steps, EI couldn't satisfy them.

Added acceptance_criteria field to SystemPlan (default="" for compat). SA prompt instructs model to produce verifiable outcomes. EI feeds task_plan.acceptance_criteria to SA when generating exit_plan.

**Files:** systems_architect_prompt.md, exit_interview_specialist.py, _orchestration.py

---

### a512c77 — 2026-02-15 17:12 — fix(orchestrator): clear stale error on recovery (#188)

scratchpad error/error_report from a prior specialist failure persisted via dict merge across all subsequent steps. Clear them when routing to Facilitator for retry.

**Files:** graph_orchestrator.py

---

### 461bd2b — 2026-02-15 20:44 — fix(sa-prompt): sharpen acceptance_criteria toward observable outcomes (#193)

Second live run showed SA writing process-oriented criteria ("all file movements are logged with no errors") instead of outcome-oriented criteria. PD doesn't produce movement logs, so EI couldn't verify, looped 3x. Prompt now distinguishes externally observable outcomes from internal process state.

**Files:** systems_architect_prompt.md

---

### d341729 — 2026-02-15 22:15 — fix(ei): unify completion guard — enforce tool use before evaluation (#193)

Two completion paths (react_step `completed` flag and DONE tool call) converged into a single guard. Model was calling DONE immediately on iteration 0 without using any verification tools.

**Files:** exit_interview_specialist.py

---

### 8b4fd6f — 2026-02-16 02:19 — refactor(ei): react_step-only verification, shared artifact tools (#195, #196)

Remove the single-pass LLM fallback path from EI. The fallback was a silent failure mode — when prompt-prix was unavailable, EI evaluated completion by reading summaries and produced credible-sounding false negatives that burned iteration budgets.

Extract list_artifacts/retrieve_artifact to mcp/artifact_tools.py (shared module). max_iterations now config-driven. ~730 → ~500 lines. 49 unit tests.

Closes #195, closes #196.

**Files:** exit_interview_prompt.md, __init__.py, artifact_tools.py, exit_interview_specialist.py, test_artifact_tools.py, test_exit_interview_specialist.py, config.yaml, TEST_SUITE_SUMMARY.md, EXIT_INTERVIEW.md

---

### d7592cc — 2026-02-16 11:21 — refactor(pipeline): Triage→SA flip, ACCEPT/REJECT classifier, Facilitator context assembly (#197, #199)

Pipeline entry flipped from SA→Triage to Triage→SA→Facilitator→Router. Triage now runs FIRST as a pure ACCEPT/REJECT gate — rejection via ask_user fires before SA invests an LLM call on planning.

Triage rewritten from context-gathering action planner to classifier. Schema fix: output_model_class=ContextPlan instead of tools=[ContextPlan].

Facilitator no longer returns error on empty triage_actions. Context assembly runs unconditionally. State serializer reads react_trace from current update only, preventing stale traces from prior specialists bleeding into snapshots.

**Files:** triage_architect_prompt.md, facilitator_specialist.py, triage_architect.py, state_serializer.py, graph_builder.py, graph_orchestrator.py, context_engineering.py, test_clarification_workflow.py, test_context_engineering_graph.py, test_facilitator.py, test_graph_orchestrator.py, test_triage_architect.py, config.yaml, TEST_SUITE_SUMMARY.md

---

### 98180a0 — 2026-02-16 11:22 — feat(frontend): STATE tab inspector with snapshot paging + CSS bleed fix (#184, #198)

STATE tab now has INSPECTOR/RAW sub-views. Inspector shows per-specialist snapshots with paging controls. CSS bleed fix: artifact content now renders via textContent instead of innerHTML/marked.parse().

**Files:** app.js, index.html, style.css

---

### 0e4ca86 — 2026-02-16 11:22 — chore(infra): mount prompt-prix test volume for eval battery

**Files:** docker-compose.yml

---

## Issues Created/Updated (last 30 hours)

### New Issues Filed

| # | Title | State | Labels |
|---|-------|-------|--------|
| #199 | Flip entry pipeline: Triage before SA (gate before investment) | OPEN | enhancement |
| #198 | BUG-UI-001: HTML artifact CSS bleeds into master UI layout | OPEN | bug |
| #197 | Clean up Triage: triage_actions pattern is vestigial | OPEN | tech-debt |
| #196 | feat: config-driven max_iterations for all react_step specialists | CLOSED | enhancement |
| #195 | Refactor: Re-architect EI — kill non-ReAct path, extract artifact tools | CLOSED | bug, refactor |
| #194 | Naming drift: acceptance_criteria vs exit_plan vs Success Criteria | OPEN | bug |
| #193 | SA acceptance_criteria produces process criteria instead of observable outcomes | OPEN | bug |
| #192 | Clean up 2 permanently-skipped unit tests | OPEN | bug |
| #191 | BUG-STATE-191: Ghost specialist 'filesystem' in recommended_specialists | OPEN | bug |
| #190 | BUG-TIMELINE-190: react_step specialists show no prompts in state_timeline | OPEN | bug |
| #189 | BUG-TIMELINE-189: Facilitator entries missing from state_timeline | OPEN | bug |
| #188 | BUG-STATE-188: Stale error_report persists in scratchpad after recovery | OPEN | bug |
| #187 | BUG-TIMELINE-187: Loop detection decision not captured in state_timeline | OPEN | bug |
| #186 | BUG-ARCHIVER-001: Report header hardcodes 'Completed Successfully' | OPEN | bug |
| #185 | requires_artifacts config gate not enforced by SafeExecutor | OPEN | bug |
| #184 | feat(observability): State timeline snapshots via SSE and archive | OPEN | enhancement |

### Issue Details

**#199 — Flip entry pipeline: Triage before SA**
Invert from SA→Triage to Triage→SA→Facilitator→Router. Three problems with old order: (1) rejection must precede investment, (2) task_plan biases Triage toward acceptance, (3) SA may hallucinate from underspecified prompts.

**#198 — CSS bleed**
CSS from HTML artifacts escaping container and corrupting Vegas Terminal UI. Global CSS selectors in artifact HTML override parent styles. Fix: render via textContent, RENDER/SAVE buttons for viewing in new tab.

**#197 — Vestigial triage_actions**
triage_actions in scratchpad drives dead conditionality. check_triage_outcome() routes to Facilitator or Router based on actions, but Triage rarely produces meaningful actions. Facilitator should always run.

**#196 — Config-driven max_iterations** (CLOSED)
All react_step specialists now read max_iterations from config.yaml. EI changed from hardcoded module constant to config-driven. Pattern: `specialist_config.get("max_iterations", DEFAULT)`.

**#195 — EI re-architecture** (CLOSED)
Kill non-ReAct fallback path. It was a silent failure mode producing credible-sounding false negatives. Extract artifact tools to shared module. ~730→~500 lines.

**#194 — Naming drift**
Four names for same concept: acceptance_criteria (task_plan field), exit_plan (artifact name), execution_steps (exit_plan content), "Success Criteria" (EI prompt label). Creates tracing confusion.

**#193 — SA process vs outcome criteria**
SA wrote "all file movements are logged with no errors" — PD doesn't produce movement logs. EI couldn't verify process criteria, looped 3x. Prompt sharpened to distinguish observable outcomes from internal process.

**#192 — 2 skipped tests**
test_install_script (setUp path resolution) and test_dispatch_timeout_error (signal.alarm flaky under pytest). Permanently skipped = dead code.

**#191 — Ghost 'filesystem' specialist**
EI writes recommended_specialists: ["filesystem"] — doesn't exist. Persists at top-level GraphState. No validation against registered specialist roster.

**#190 — react_step prompt invisibility**
PD/TA show model_id: "no_llm_call" in state_timeline. Actual prompts happen inside prompt-prix MCP, invisible to timeline. Most active specialists have least prompt visibility.

**#189 — Facilitator missing from timeline**
8 Facilitator executions visible in routing_history have no corresponding state_timeline entries. Facilitator is the sole gathered_context writer — its output determines what every specialist sees.

**#188 — Stale error persistence**
scratchpad error/error_report from prior specialist failure persists via ior merge across all subsequent steps. First error wins permanently. Fix: clear on recovery routing. Partially fixed in a512c77.

**#187 — Loop detection invisible in timeline**
_is_unproductive_loop() decisions not recorded in state_timeline im_decision field. Loop detector is the most consequential IM decision but invisible in forensics.

**#186 — Archiver success header**
Report says "Completed Successfully" even when terminated via circuit breaker. termination_reason exists in manifest but report template doesn't use it.

**#185 — requires_artifacts not enforced**
config.yaml declares requires_artifacts but gate in SafeExecutor doesn't fire for Facilitator. Enforcement code exists in node_executor.py:113-132. Only active user is summarizer_specialist.

**#184 — State timeline feature**
Per-specialist state snapshots via SSE + archive. Culmination of resume_trace saga: observability data must not live in state that models consume. Follows llm_traces write-only pattern.

---

## Uncommitted Work (this session)

### Facilitator accumulated_work
- `_accumulate_prior_work()`, `_build_task_context()`, `_build_prior_work_section()` — three new helpers
- Both BENIGN and normal retry paths use shared helpers
- `accumulated_work` artifact persists PD's specialist_activity across passes
- 4 new tests in test_facilitator_retry.py
- 867 tests passing, 2 skipped

### ADR-CORE-076_Data-Flow-Primitives.md (proposed)
- Inventories existing data flow primitives (artifact tools, requires_artifacts, artifact_providers, specialist_activity, gathered_context, routing signals, decline pattern)
- Identifies missing `write_artifact` primitive
- Frames design questions: namespacing, WRITABLE_ARTIFACTS interaction, Facilitator role evolution, accumulated_work redundancy
- Documents resume_trace lineage and "jazz in the rests" problem

### Uncommitted files
- config.yaml (modified)
- docker-compose.yml (modified)
- scripts/run_tier1_battery.sh (new)
- scripts/run_tier2_eval.py (new)
