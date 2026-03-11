# ADR-CORE-036: Exit Interview Pattern (Task Completion Detection)

**Status:** COMPLETED (Phase 1 implemented; see ADR-CORE-058 for Phase 2 evolution)
**Date:** 2025-12-25 | Updated: 2026-02-01
**Context:** Issue #7 investigation revealed gap in task completion detection

---

## Implementation Status

**Phase 1 COMPLETE.** ExitInterviewSpecialist implemented and wired into graph.

- Gates END node via `check_task_completion()` → `exit_interview_specialist`
- Evaluates completion using LLM judgment against original request
- Routes INCOMPLETE back through Facilitator for context refresh (Issue #96)

**Known Limitation (Issue #97):** Exit Interview only sees artifact **keys**, not contents. For file operations, it cannot verify actual filesystem state. This leads to false COMPLETE verdicts when specialists claim success but work is incomplete.

**Phase 2 (ADR-CORE-058):** Evolves Exit Interview into a verification orchestrator that delegates verification planning to systems_architect and executes atomic sub-checks.

---

## Problem

Currently, specialists decide for themselves whether to set `task_is_complete: True`. This creates two problems:

1. **Specialists lack context**: A specialist doesn't know if its output is the final deliverable or an intermediate step. `systems_architect` can't know if "create a plan" IS the task vs. "plan is needed for web_builder."

2. **Inconsistent patterns**: Some specialists always set it (chat, data_extractor), some never do (systems_architect, web_builder), some conditionally (critic on ACCEPT).

### Observed Failure

```
User: "Create a brief plan for a hello world web page"
Flow: triage → systems_architect → default_responder
Problem: systems_architect produces plan but doesn't set task_is_complete
         Router routes to default_responder instead of END
```

systems_architect can't know that producing a plan completes THIS task, because in other contexts (e.g., "build a web page"), the plan feeds into web_builder.

---

## Observation: Gemini's Final Check Pattern

Multi-agent systems (observed in Gemini reasoning traces) typically include inter-agent checks AND a "final check" paragraph that evaluates whether the overall task is complete before closing.

This separates:
- **Doing the work** (specialist executes)
- **Deciding if work is done** (exit interview evaluates)

---

## Proposed Solution: Exit Interview

Add a post-execution checkpoint after each specialist (or after non-routing specialists) that evaluates task completion.

### Flow

```
User Request
    ↓
Triage → Specialist A executes
    ↓
[EXIT INTERVIEW]
├─ Inputs: original request, current artifacts, messages, routing history
├─ Evaluates: "Does what we have satisfy the original request?"
├─ Decision: COMPLETE → END | CONTINUE → Router
    ↓
(if CONTINUE) Router → Specialist B executes
    ↓
[EXIT INTERVIEW]
...
```

### Implementation Options

#### Option A: Dedicated ExitInterviewSpecialist

```python
class ExitInterviewSpecialist(BaseSpecialist):
    """Evaluates whether the task is complete after each specialist execution."""

    def _execute_logic(self, state):
        original_request = state["messages"][0].content  # First user message
        artifacts = state.get("artifacts", {})

        # LLM evaluates: does current state satisfy original request?
        prompt = f"""
        Original request: {original_request}

        Current artifacts: {list(artifacts.keys())}

        Is this task complete? Consider:
        - Did the user ask for a specific deliverable?
        - Does that deliverable now exist?
        - Is there remaining work implied by the request?

        Respond with: COMPLETE or CONTINUE (with reason)
        """

        decision = self.llm_adapter.invoke(...)

        if decision == "COMPLETE":
            return {"task_is_complete": True}
        else:
            return {}  # Router will pick next specialist
```

**Pros:** Explicit, testable, observable
**Cons:** Extra LLM call per specialist, latency

#### Option B: Router Incorporates Exit Interview

Extend Router to check completion before routing:

```python
def _execute_logic(self, state):
    # First: evaluate if task is complete
    if self._is_task_complete(state):
        return {"task_is_complete": True, "next_specialist": END}

    # Otherwise: route to next specialist
    ...
```

**Pros:** No extra specialist, single decision point
**Cons:** Router becomes more complex, conflates routing with completion

#### Option C: Graph Edge Condition

Add conditional edge after specialist execution:

```python
def after_specialist(state):
    if exit_interview_says_complete(state):
        return END
    return "router"
```

**Pros:** Clean graph structure, explicit in flow
**Cons:** Adds complexity to graph builder

#### Option D: Procedural Check (No LLM)

Simple heuristic: if specialist produced an artifact matching a pattern in the original request, task is complete.

```python
def check_completion(state):
    request = state["messages"][0].content.lower()
    artifacts = state.get("artifacts", {})

    # Heuristic matching
    if "plan" in request and "system_plan" in artifacts:
        return True
    if "html" in request and any(k.endswith(".html") for k in artifacts):
        return True
    return False
```

**Pros:** Fast, no LLM cost, deterministic
**Cons:** Brittle, doesn't handle nuanced requests

---

## Recommendation

**Option A (ExitInterviewSpecialist)** for correctness, with caching/optimization to reduce LLM calls:

1. Skip exit interview for specialists that always complete (chat, default_responder)
2. Skip if `task_is_complete` already set by specialist
3. Use fast/cheap model for exit interview (e.g., Haiku-class)

This maintains the principle that specialists don't need to know about each other or the full task context.

---

## Impact on Current Specialists

With Exit Interview pattern:
- **systems_architect**: Remove `task_is_complete` decision. Just produce plan, forbid self.
- **web_builder**: Remove critique-loop coupling. Just produce HTML, forbid self.
- **All producers**: Focus on producing artifacts, let Exit Interview decide completion.

Specialists become simpler: do your job, report what you produced, exit.

---

## Open Questions

1. **Where in graph?** After every specialist? Only after "producing" specialists?
2. **Performance**: How to minimize LLM calls for exit interview?
3. **Edge cases**: What if exit interview is wrong? Retry mechanism?
4. **Triage integration**: Should Triage set expected deliverables that Exit Interview checks against?

---

## Implementation Progress

### Schema Infrastructure (2025-12-27)

Created `app/src/specialists/schemas/_exit_interview.py` as foundational infrastructure:

```python
EXIT_INTERVIEW_ARTIFACTS: Dict[str, ExitInterviewArtifactConfig] = {
    "system_plan": ExitInterviewArtifactConfig(mode="present"),
    "image_description": ExitInterviewArtifactConfig(
        mode="context",
        context_prompt="Please use this image analysis to help with the user's original request.",
    ),
}
```

**Two modes defined:**
- `present`: Show artifact content directly to user (e.g., system_plan)
- `context`: Inject artifact as LLM context for response generation (e.g., image_description)

**Current state:**
- Schema is in place and exported via `specialists/schemas/__init__.py`
- Temporary fix in DefaultResponder was removed (DefaultResponder should be purely conversational)
- Exit Interview requires a **dedicated graph node** that can conditionally route to END or back to Router

**Key insight:** Exit Interview cannot be implemented in EndSpecialist because that's the terminal node - it can't route elsewhere. The pattern requires a graph node positioned AFTER specialists but BEFORE the terminal decision:

```
Specialist → ExitInterview → {END | Router}
```

**Next step:** Add ExitInterview node to graph builder with conditional routing edge.

---

## Implementation Design (2025-12-27)

### Traced Root Cause: Artifacts Never Reach User

```
User: "describe this image"
  ↓
triage_architect → image_specialist → default_responder → end_specialist
  ↓
Result: image_description artifact archived, user sees generic fallback
```

**Code trace:**
1. `image_specialist` sets `artifacts["image_description"]`, does NOT set `task_is_complete`
2. `check_task_completion` routes to Router (no completion flag)
3. Router picks `default_responder` (purely conversational, ignores artifacts)
4. `end_specialist._synthesize_response()` reads only from `user_response_snippets`, not artifacts

**The gap:** `artifact` → (nothing bridges) → `user_response_snippets` → `final_response`

### Design Decisions

1. **`task_is_complete` as hint, not directive** - Same as `recommended_next_specialists`. Exit Interview makes the actual call.

2. **CONTINUE routes to Facilitator/Triage, not Router** - Router just dispatches; Triage can evaluate what's missing and re-plan.

3. **Same model as Router** (`lmstudio_router` / gpt-oss-20b) - Proven reliable with structured prompts.

4. **Artifact previews in prompt** - No tool calls. Exit Interview needs to see ALL artifacts to decide which one satisfies the request.

### Graph Wiring

```python
# Current:
Specialist → check_task_completion → { END, Router }

# Proposed:
Specialist → EXIT_INTERVIEW → { END, Facilitator/Triage }
```

### Prompt Design (Router-style)

```markdown
You evaluate whether the user's original request has been satisfied.

**Your Decision-Making Process:**
Follow these rules in exact order.

1. **Check for Snippets:** If `user_response_snippets` already has substantive
   content, the task is COMPLETE. No artifact surfacing needed.

2. **Match Artifact to Request Type:**
   - "describe/explain/analyze X" + description/explanation artifact → COMPLETE
   - "fix/implement/build X" + analysis/plan artifact → CONTINUE (not deliverable)
   - "create a plan for X" + system_plan artifact → COMPLETE

3. **Check Artifact Quality:** If artifact is error message, empty, or placeholder → CONTINUE.

4. **Default:** When uncertain → CONTINUE.

**Quick Reference:**
| Request Pattern | Artifact Key | Decision |
|-----------------|--------------|----------|
| "describe this image" | image_description | COMPLETE |
| "fix this bug" | bug_analysis | CONTINUE |
| "create a plan" | system_plan | COMPLETE |
| "build X" | system_plan | CONTINUE |

You MUST output your decision by calling the `ExitDecision` tool.
```

### Schema

```python
class ExitDecision(BaseModel):
    decision: Literal["complete", "continue"]
    artifact_to_surface: Optional[str]  # artifact key, if complete
    missing: Optional[str]              # what's needed, if continue
```

### Files to Modify

1. **NEW:** `app/src/specialists/exit_interview_specialist.py`
2. **NEW:** `app/prompts/exit_interview_prompt.md`
3. **MODIFY:** `app/src/workflow/graph_builder.py` - Wire Exit Interview after specialists
4. **MODIFY:** `app/config/specialists.yaml` - Add config bound to `lmstudio_router`

### Test Expectations

1. **Image description surfaces:** `image_specialist` → `exit_interview(COMPLETE)` → user sees description
2. **Plan request completes at plan:** `systems_architect` → `exit_interview(COMPLETE)` → user sees plan
3. **Build request continues past plan:** `systems_architect` → `exit_interview(CONTINUE)` → `web_builder`
4. **Loop prevention:** Max iterations → graceful termination

### Open Questions

1. Does Facilitator need a "delta gathering" mode for CONTINUE path?
2. Loop prevention: max iterations check in graph?
3. Performance: LLM call per specialist acceptable for v1?

---

## References

- Issue #7: Routing loop investigation surfaced this gap
- Gemini reasoning traces: "final check" pattern observed
- ADR-CORE-016: Menu Filter (related orchestration pattern)
