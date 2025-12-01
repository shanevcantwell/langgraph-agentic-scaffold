# Deep Research: HitL Integration Addendum

**Date**: 2025-11-30
**Context**: Following the Falsification → Dialectic exchange, this document identifies a structural improvement to the "Fail Loudly" pattern proposed in the Dialectic.

---

## The Gap in "Fail Loudly"

The Dialectic (Dialectic 6) proposes this error handling:

> **Protocol:**
> 1. `WebSpecialist` returns `{"error": "No results found"}` or an empty list.
> 2. The `SystemPlan` has an `error_handler` field (or the Orchestrator defaults to Architect).
> 3. The Architect receives the error.
> 4. The Architect's prompt explicitly instructs: "If a step fails, do not hallucinate. Ask the user for a new direction."

**The Problem**: Step 4 relies on **LLM prompt compliance**. This is a soft guarantee that depends on:
- The model following instructions
- The prompt being unambiguous
- No context pressure causing the model to "help anyway"

This is the same class of problem the escape hatches (`PROMPT_ESCAPE_HATCH_MANIFEST.md`) address at the prompt level. But for pipeline failures, we can do better with **structural guarantees**.

---

## The Structural Alternative: ADR-CORE-018 HitL Clarification

ADR-CORE-018 (`docs/ADRs/in-progress/ADR-CORE-018-HitL-Clarification-Flow.md`) proposes:

1. **PostgreSQL + pgvector** for LangGraph checkpointing
2. **`interrupt_before`** to pause graph execution at specific nodes
3. **DialogueSpecialist** to present clarification questions with context
4. **Thread-based resumption** via `/resume` endpoint

This provides a **code-enforced guarantee** that:
- The graph WILL pause when clarification is needed
- State WILL be preserved (checkpoint, not artifact hope)
- User response WILL resume from exact graph state
- No LLM can "decide to help anyway" and hallucinate

---

## Proposed Integration

### StepResult Schema Extension

```python
class StepResult(BaseModel):
    """Result from a pipeline step execution."""
    status: Literal["success", "failed", "clarification_required"]
    result: Optional[Any] = None
    error: Optional[str] = None

    # Hook for CORE-018 HitL
    clarification_question: Optional[str] = None
    clarification_context: Optional[dict] = None  # Gathered context to show user
```

### Orchestrator Logic

```python
# In GraphOrchestrator.execute_plan_step()
step_result = await self._execute_step(current_step)

if step_result.status == "clarification_required":
    # Store question in state for DialogueSpecialist
    state["scratchpad"]["pending_clarification"] = {
        "question": step_result.clarification_question,
        "context": step_result.clarification_context,
        "resume_step": current_step.step_number,
        "plan_id": system_plan.id
    }
    # Route to dialogue_specialist - graph will checkpoint here
    return "dialogue_specialist"
```

### Deep Research Scenarios with HitL

| Scenario | Dialectic Approach | With HitL Hook |
|----------|-------------------|----------------|
| **Search returns 0 results** | Error → Architect prompt says "ask user" | `clarification_required` → graph pauses → "No results for X. Try different terms?" |
| **"Best" is undefined** | Architect guesses "popularity" | `clarification_required` → graph pauses → "Best for what? Speed, accuracy, cost?" |
| **Relevance uncertain** | Synthesizer guesses | `clarification_required` → graph pauses → "Found 3 results. Which are relevant to your goal?" |
| **Pipeline step fails** | Error bubbles to Architect | `clarification_required` → graph pauses at failure point → user redirects |
| **Partial results** | Continue with what we have | `clarification_required` → "Found 3 of 5 requested. Continue or retry?" |

---

## Alignment with Broader Architecture

### ESM Connection

The ESM-Foundry (`docs/ADRs/proposed/emergent_state_machine/`) proposes the same pattern:

> **HIL Execution Strategy**: Utilizes LangGraph's `interrupt_after` feature. The consumer specifies which nodes trigger an interrupt. Execution pauses after the specified nodes, checkpoints the state, and returns control to the caller.

The Deep Research `clarification_required` status is a **trigger condition** for ESM's HIL strategy.

### Cathedral Connection

The Whetstone Process (`docs/PLANS/cathedral-and-codex/ADR-EDUCATION-001_ The Whetstone Process.md`) describes iterative refinement:

> **The Sharpening Stroke (The Iterative Dialogue):** Each back-and-forth interaction is a "sharpening stroke" where the user's idea is ground against the AI's logic and structure.

HitL clarification IS the Whetstone Process at the infrastructure level:
- Graph pauses = "Lay the Blade on the Stone"
- User clarifies = "The Sharpening Stroke"
- Graph resumes with enriched context = "Wiping the Blade"
- Final output = "The Final Polish (The Artifact)"

Without HitL infrastructure, the Whetstone Process must be simulated through prompt engineering. With HitL, it's **structurally enforced**.

---

## Implementation Dependency

**CORE-018 is a prerequisite for robust Deep Research error handling.**

The minimal path:
1. Implement CORE-018 Part 1 (PostgreSQL checkpointing)
2. Implement CORE-018 Part 3 (DialogueSpecialist)
3. Add `clarification_required` status to StepResult
4. Wire Orchestrator to route to DialogueSpecialist on clarification

This can proceed in parallel with Deep Research Phase 1 (WebSpecialist primitive), converging when pipeline execution is implemented.

---

## Questions for Gemini

1. **Dependency Ordering**: Should CORE-018 HitL infrastructure be a hard prerequisite for Deep Research pipeline execution, or accept "prompt compliance" for Phase 1 and upgrade later?

2. **Clarification Granularity**: Should `clarification_required` be:
   - Per-step (WebSpecialist can request clarification)
   - Per-plan (only Architect can request clarification)
   - Both (with escalation rules)

3. **State Preservation on Resume**: When graph resumes after clarification, should:
   - The failed step retry with new context
   - The plan re-execute from the beginning
   - The Architect re-plan based on clarification

4. **ICSP Integration**: The ICSP Protocol (Cathedral) is about challenging assumptions. Should `clarification_required` be the mechanism for ICSP intervention, or is that a separate concern?

---

## Summary

The Dialectic's "Fail Loudly" is directionally correct but relies on LLM compliance. ADR-CORE-018's HitL Clarification flow provides the **structural guarantee** that makes it robust.

**Recommendation**: Add `clarification_required` as a first-class status in Deep Research, with hooks into CORE-018's DialogueSpecialist and checkpoint/resume infrastructure. This transforms "hope the LLM asks" into "the graph will pause and ask."
