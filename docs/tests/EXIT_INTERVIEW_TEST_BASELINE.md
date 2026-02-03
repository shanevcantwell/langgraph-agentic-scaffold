# Exit Interview Test Baseline

**Created:** 2026-02-03
**Purpose:** Track test assertions for `task_is_complete` before and after Issue #107 (Exit Interview kludge fix)

---

## Background

Per ADR-CORE-036 (Exit Interview Pattern), specialists do NOT decide task completion. Exit Interview is the sole authority. However, tests written pre-Exit-Interview expect specialists to set `task_is_complete`. This document tracks which tests need updating.

**Source of Truth:** [ARCHITECTURE.md](../ARCHITECTURE.md) § 5.3 Four-Stage Termination

---

## Test Categories

### A. Terminal Specialists (KEEP assertions)

These specialists ARE terminal points - their assertions are architecturally correct.

| File | Specialist | Lines | Assertion |
|------|------------|-------|-----------|
| `test_tiered_synthesizer_specialist.py` | TieredSynthesizer | 56, 96, 132, 294 | `task_is_complete is True` |
| `test_default_responder_specialist.py` | DefaultResponder | 45, 67 | `task_is_complete is True` |
| `test_chat_specialist.py` | ChatSpecialist | 50 | `task_is_complete is True` |

**Rationale:** Join nodes and terminal responders legitimately signal completion.

---

### B. Non-Terminal Specialists (REMOVE assertions after #107)

These specialists should NOT set `task_is_complete`. Tests need updating.

| File | Specialist | Lines | Current Assertion | Post-#107 |
|------|------------|-------|-------------------|-----------|
| `test_batch_processor_specialist.py` | BatchProcessor | 85, 137, 147, 164, 252 | `task_is_complete is True` | Assert NOT in result |
| `test_text_analysis_specialist.py` | TextAnalysis | 122 | `task_is_complete is True` | Assert NOT in result |
| `test_structured_data_extractor.py` | StructuredDataExtractor | 57 | `task_is_complete is True` | Assert NOT in result |
| `test_critic_specialist.py` | Critic (ACCEPT path) | 58 | `task_is_complete is True` | Assert NOT in result |

**Total assertions to change:** 9

### B.1 Specialists Without Test Coverage for task_is_complete

These specialists set `task_is_complete` but their tests don't assert on it. Only the specialist needs fixing.

| Specialist File | Line | Test File | Test Coverage Gap |
|-----------------|------|-----------|-------------------|
| `data_extractor_specialist.py` | 67 | `test_data_extractor_specialist.py` | No assertion on task_is_complete |

### B.2 Deprecated Specialists (DELETE with #92)

These will be removed entirely, not fixed.

| Specialist File | Lines |
|-----------------|-------|
| `distillation_coordinator_specialist.py` | 435 |
| `distillation_response_collector_specialist.py` | 143 |

---

### C. Exit Interview (KEEP - THE authority)

| File | Lines | Assertion |
|------|-------|-----------|
| `test_exit_interview_specialist.py` | 224, 252 | `task_is_complete is False` (INCOMPLETE) |
| `test_exit_interview_specialist.py` | 289 | `task_is_complete is True` (COMPLETE) |

**Rationale:** Exit Interview IS the completion authority. These are correct.

---

### D. Progenitors (already correct)

These tests already assert that progenitors do NOT set task_is_complete.

| File | Specialist | Lines | Assertion |
|------|------------|-------|-----------|
| `test_progenitor_alpha_specialist.py` | Alpha | 86, 88 | `task_is_complete not in result` or `None/False` |
| `test_progenitor_bravo_specialist.py` | Bravo | 86, 88 | `task_is_complete not in result` or `None/False` |

**Rationale:** These are the model for non-terminal specialists.

---

### E. Integration Tests (KEEP - check end state)

These tests check final workflow state, which includes Exit Interview.

| File | Lines | Notes |
|------|-------|-------|
| `test_tiered_chat_end_to_end.py` | 117, 216, 301 | Full workflow - Exit Interview sets completion |
| `test_specialist_routing_matrix.py` | 201, 211 | End-to-end - completion from Exit Interview |
| `test_image_workflow_quality.py` | 314 | Archive inspection - completion from Exit Interview |

**Rationale:** Integration tests check the full pipeline. Exit Interview will set `task_is_complete`.

---

### F. Test Fixtures (OK - initial state)

These set `task_is_complete: False` as initial test state. No changes needed.

| File | Count |
|------|-------|
| `test_router_specialist.py` | 1 |
| `test_node_executor.py` | 3 |
| `test_parallel_state_logic.py` | 4 |
| `test_artifact_passing.py` | 8 |
| `test_tiered_chat_end_to_end.py` | 5 |
| `test_menu_filter_pattern.py` | 11 |

---

## Pre-#107 Checklist

Before fixing Issue #107 (graph wiring), verify:

- [ ] All Category B tests identified and tracked
- [ ] No hidden `task_is_complete` assertions in other test files
- [ ] Integration tests understood (they should pass after #107)

## Post-#107 Checklist

After fixing Issue #107:

- [ ] Remove `task_is_complete` from 5 specialists (batch_processor, text_analysis, structured_data_extractor, critic, data_extractor)
- [ ] Update 9 test assertions to expect NOT set (Category B)
- [ ] Verify integration tests still pass (Exit Interview sets completion)
- [ ] Progenitor tests remain green (already correct)
- [ ] Delete distillation specialists (#92) - removes 2 more occurrences

---

## Summary: Specialist Inventory

| Category | Specialists | Action | Test Impact |
|----------|-------------|--------|-------------|
| **Terminal (correct)** | chat, default_responder, tiered_synthesizer | Keep | Keep 7 assertions |
| **Exit Interview** | exit_interview | Keep (authority) | Keep 3 assertions |
| **Non-terminal (fix)** | batch_processor, text_analysis, structured_data_extractor, critic | Remove signal | Update 9 assertions |
| **No test coverage** | data_extractor | Remove signal | No test change |
| **Deprecated** | distillation_coordinator, distillation_response_collector | Delete (#92) | Delete tests |

**Totals:**
- 14 specialists set `task_is_complete`
- 4 are terminal (correct)
- 1 is Exit Interview (authority)
- 5 need fixing (remove signal)
- 2 need deletion (deprecated)
- 2 correctly do NOT set (progenitors)

---

## Related Issues

| Issue | Description | Status |
|-------|-------------|--------|
| #107 | Replace Exit Interview intercept kludge | OPEN |
| #94 | Specialist audit (remove task_is_complete) | OPEN, blocked by #107 |
| #93 | data_extractor_specialist specific | OPEN |
| #92 | Remove deprecated distillation architecture | OPEN |
