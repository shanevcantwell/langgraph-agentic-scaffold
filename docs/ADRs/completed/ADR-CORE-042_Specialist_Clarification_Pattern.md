# ADR-CORE-042: Specialist Clarification Pattern ("Raise Hand")

**Status:** Completed
**Created:** 2024-12-27
**Context:** Observed during image_specialist execution requesting UI clarification
**Prerequisites:** ADR-CORE-018 (implemented 2026-01-20)

## Implementation Status (2026-01-20)

**Foundation ready:** ADR-CORE-018 implemented the interrupt/resume infrastructure:
- `MemorySaver` checkpointing
- `/v1/graph/resume` endpoint
- UI interrupt handling (Gradio + web-ui clarification modals)
- `CLARIFICATION_REQUIRED` event type

**Not yet implemented:** The "Option B" pattern where any specialist can emit `ClarificationRequest` that routes to a central handler. Currently only `DialogueSpecialist` (in Facilitator phase) can call `interrupt()`.

---

## Problem Statement

Currently, only the Facilitator (via DialogueSpecialist) can pause workflow execution to request user clarification using LangGraph's `interrupt()` mechanism. Once a request passes Facilitator and enters the routing/execution phase, specialists are "fire and forget" - they must either complete their task or emit a response asking for more information.

**Observed behavior:** When image_specialist received a request to "make this gradio look more like the image," it had the task but lacked specific details (colors, fonts, layout preferences). Its only option was to emit a clarifying question as its response, which:
1. Routes back through Router → default_responder → end
2. Completes the workflow
3. Requires a new user turn to provide the answer
4. Loses the specialist's execution context

## Current Architecture

```
User → Triage → Facilitator → Router → Specialist → Router → End
                    ↑
                interrupt() lives here only
```

The Facilitator is the designated "intake" checkpoint. The assumption: once past Facilitator, the task is well-defined enough to execute without further clarification.

## Proposed Options

### Option A: Specialist-Level Interrupt (Direct)

Allow any specialist to call `interrupt()` directly, pausing the workflow at that specialist.

```python
class ImageSpecialist(BaseSpecialist):
    def execute(self, state: GraphState) -> GraphState:
        if self._needs_clarification(state):
            # Pause workflow, wait for user input
            clarification = interrupt({
                "type": "clarification_needed",
                "specialist": "image_specialist",
                "questions": ["What colors?", "What layout?"]
            })
            # Resume here with user's answer
            state.scratchpad["user_clarification"] = clarification
        # Continue execution...
```

**Pros:**
- Simple mental model: any specialist can ask questions
- Preserves specialist context across the interrupt
- Uses existing LangGraph interrupt mechanism

**Cons:**
- Every specialist needs interrupt-awareness
- Checkpointing required everywhere (state persistence)
- Harder to reason about workflow state ("where is it paused?")
- Specialists become stateful, complicating testing

### Option B: ClarificationSpecialist (Centralized)

Specialists that need clarification route to a dedicated ClarificationSpecialist, which handles the interrupt and routes back.

```
User → Triage → Facilitator → Router → ImageSpecialist
                                              ↓
                                    (needs clarification)
                                              ↓
                              ClarificationSpecialist ← interrupt()
                                              ↓
                                    (user responds)
                                              ↓
                              Router → ImageSpecialist (with answer)
```

**Pros:**
- Single point of interrupt logic (easier to maintain)
- Specialists remain stateless/simple
- Clear separation: specialists do work, ClarificationSpecialist handles HitL
- Fits existing routing pattern

**Cons:**
- Context must be serialized into state for handoff
- Two specialist invocations for one logical task
- ImageSpecialist must handle "initial" vs "resumed with answer" cases

### Option C: Enhanced Facilitator Pre-Check

Expand Facilitator's role to proactively identify tasks likely to need clarification before routing.

```python
# Facilitator logic
if task_type == "image_customization" and not has_specific_details(request):
    # Ask clarifying questions BEFORE routing to specialist
    questions = get_clarification_questions_for_task_type(task_type)
    return interrupt({"questions": questions})
```

**Pros:**
- No changes to specialist architecture
- Keeps interrupt logic in one place
- Proactive vs reactive clarification

**Cons:**
- Facilitator becomes a bottleneck of domain knowledge
- Can't anticipate all specialist-specific clarification needs
- Some clarifications only become apparent during execution

### Option D: Hybrid - Soft Clarification via State

Specialists emit "soft" clarification requests via state, which the UI interprets as a prompt for more info on the next turn.

```python
# Specialist sets state flag
state.scratchpad["pending_clarification"] = {
    "from": "image_specialist",
    "questions": ["What colors?", "Layout preferences?"],
    "resume_context": {...}  # Serialized context for next turn
}
```

**Pros:**
- No interrupt mechanism needed
- Works with current architecture
- UI can choose how to present clarification request

**Cons:**
- User must explicitly continue (new message)
- Context serialization/deserialization complexity
- Not a true "pause" - workflow completes, then restarts

## Recommendation

**For v2, implement Option B (ClarificationSpecialist)** with the following design:

1. Specialists can emit a structured `ClarificationRequest` in their output
2. Router recognizes this and routes to `ClarificationSpecialist`
3. ClarificationSpecialist calls `interrupt()` and waits
4. On resume, Router routes back to the original specialist with the answer injected into state
5. Original specialist detects "resumed with clarification" and continues

This keeps:
- Interrupt logic centralized (one specialist handles HitL)
- Specialists mostly stateless (context passed via state)
- Clear architectural boundary (specialists don't directly interact with users mid-execution)

## Implementation Sketch

```python
# In specialist output
class ClarificationRequest(BaseModel):
    questions: List[str]
    context: Dict[str, Any]  # What to restore on resume

# Specialist can return this
def execute(self, state):
    if needs_more_info:
        return {"clarification_request": ClarificationRequest(...)}
    # normal execution...

# Router logic
if "clarification_request" in specialist_output:
    return "clarification_specialist"

# ClarificationSpecialist
def execute(self, state):
    request = state.scratchpad["clarification_request"]
    answer = interrupt(request.dict())
    state.scratchpad["clarification_answer"] = answer
    state.scratchpad["resume_specialist"] = request.context["original_specialist"]
    return state
```

## Open Questions

1. **Which specialists get this capability?** All of them, or a whitelist?
2. **How many clarification rounds are allowed?** Prevent infinite loops.
3. **UI implications:** How does the UI know it's a clarification vs a final response?
4. **Context size:** What happens if specialist context is too large to serialize?
5. **Internal clarification before HitL?** → See ADR-CORE-032 "Unification: The Help Needed Pattern" (lines 639-750). The capability-based routing model subsumes this: clarification becomes a `help_needed[type="clarification"]` request that InterAgentTriage can attempt to resolve internally (via capability match or MCP service) before escalating to HitL.

## Related

- ADR-CORE-018: HitL Clarification Flow (**implemented** - provides interrupt/resume infrastructure)
- ADR-CORE-032: Capability-Based Routing (**proposed** - subsumes this ADR's "Option B" into unified `help_needed[]` pattern; see "Unification" section)
- DialogueSpecialist: Current HitL implementation in Facilitator phase
- Issue #16: Image handling (where this pattern was first observed)
