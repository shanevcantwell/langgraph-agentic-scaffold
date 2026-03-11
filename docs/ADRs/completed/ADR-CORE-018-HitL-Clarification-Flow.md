# ADR-CORE-018: Human-in-the-Loop Clarification Flow

**Status**: IMPLEMENTED
**Date**: 2025-11-26
**Implemented**: 2026-01-20
**Supersedes**: None
**Related**: ADR-PLATFORM-001 (missing PostgreSQL), ADR-CORE-008 (MCP Architecture), ADR-CORE-042 (extends this to all specialists)

## Implementation Notes (2026-01-20)

**Deviation from proposal:** Uses `MemorySaver` (in-memory checkpointing) instead of `PostgresSaver`. This simplifies infrastructure but means interrupt state doesn't persist across server restarts. PostgreSQL can be added later if durable checkpointing is needed.

**Files implemented:**
- `app/src/persistence/checkpoint_manager.py` - `get_default_checkpointer()` helper
- `app/src/api.py` - Interrupt detection in `_stream_formatter`, checkpointer wiring
- `app/src/workflow/runner.py` - Thread ID propagation for resume
- `app/src/interface/ag_ui_schema.py` - `CLARIFICATION_REQUIRED` event type
- `app/src/ui/gradio_app.py` - Clarification modal and resume handling
- `app/src/ui/api_client.py` - `resume_workflow()` method
- `app/web-ui/public/index.html` - Clarification modal HTML
- `app/web-ui/public/app.js` - Interrupt event handling and resume logic

---

## Context

When TriageArchitect produces a ContextPlan with ONLY `ask_user` actions (indicating the user needs to provide more information before the system can proceed), the current routing breaks:

1. **Naming mismatch bug**: `graph_orchestrator.py:check_triage_outcome()` returns `"default_responder"` but the actual node name is `"default_responder_specialist"` - causing graph validation failure
2. **No state persistence**: Without checkpointing, context gathered during triage is lost when waiting for user clarification
3. **Conflation of concerns**: Clarification (active, directed questions) is architecturally distinct from default response (passive fallback)

### Current Flow (Broken)
```
User Request → TriageArchitect → ContextPlan{ask_user actions only}
                                         ↓
                              check_triage_outcome()
                                         ↓
                              returns "default_responder" ❌ (wrong name)
```

### FacilitatorSpecialist's Role
The existing FacilitatorSpecialist handles autonomous context gathering via MCP:
- `RESEARCH` → researcher_specialist.search()
- `READ_FILE` → file_specialist.read_file()
- `SUMMARIZE` → summarizer_specialist.summarize()
- `LIST_DIRECTORY` → file_specialist.list_files()

But `ASK_USER` is unhandled - there's no specialist to present questions to the user with context.

---

## Decision

### Part 1: Database Infrastructure (Foundation for Codex)

Add PostgreSQL + pgvector to enable:
- **Immediate**: LangGraph checkpointing via `PostgresSaver` for HitL pause/resume
- **Future**: The Codex multi-modal memory system (Working, Episodic, Semantic, Procedural)

```yaml
# docker-compose.yml addition
services:
  db:
    image: pgvector/pgvector:pg16
    container_name: langgraph-db
    environment:
      POSTGRES_USER: langgraph
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-langgraph_dev}
      POSTGRES_DB: langgraph
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langgraph"]
```

### Part 2: Separate Specialists for Distinct Concerns

**Architectural Principle**: Clarification ≠ Default

| Concern | Behavior | Specialist |
|---------|----------|------------|
| **Clarification** | Active, directed - "I need X, Y, Z from you to proceed" | NEW: DialogueSpecialist |
| **Default** | Passive fallback - "Generic response because nothing else fit" | EXISTING: default_responder_specialist |

### Part 3: DialogueSpecialist (NEW)

Purpose: Present `ask_user` questions with context from triage reasoning

Responsibilities:
- Read `context_plan.actions` where `action_type == "ask_user"`
- Format questions clearly, explain WHY information is needed
- Set `clarification_required: True` in response for API/UI signaling
- Preserve `gathered_context` from any prior facilitator execution

### Part 4: HitL Checkpointing

```python
# Graph compilation with interrupt
workflow.compile(
    checkpointer=PostgresSaver.from_conn_string(connection_string),
    interrupt_before=["dialogue_specialist"]  # Pause before presenting questions
)
```

Resume endpoint:
```python
@app.post("/v1/graph/resume")
async def resume_workflow(thread_id: str, user_input: str):
    config = {"configurable": {"thread_id": thread_id}}
    result = await workflow_runner.resume(config, user_input)
    return result
```

---

## Open Questions (For External Consultation)

1. **Should DialogueSpecialist also handle context gathering?** Or should it purely format/present questions that TriageArchitect identified?

2. **Is a separate ContextSpecialist needed?** Currently FacilitatorSpecialist gathers context via MCP. Should there be a unified abstraction?

3. **How should gathered_context flow to DialogueSpecialist?** Via:
   - Direct artifact passing (current pattern via `_get_enriched_messages`)
   - MCP service call
   - State field

4. **Should the interrupt happen BEFORE or AFTER dialogue_specialist?**
   - BEFORE: Cleaner checkpoint, specialist hasn't run yet
   - AFTER: Questions already formatted, ready for presentation

---

## Files to Modify

| File | Changes |
|------|---------|
| docker-compose.yml | Add PostgreSQL service |
| requirements.txt | Add langgraph-checkpoint-postgres, psycopg, pgvector |
| config.yaml | Add database config + dialogue_specialist |
| app/src/enums.py | Add DIALOGUE enum value |
| app/src/specialists/dialogue_specialist.py | NEW - dedicated clarification handling |
| app/src/persistence/checkpoint_manager.py | NEW - checkpoint management |
| app/src/workflow/graph_builder.py | Integrate checkpointer, add dialogue edges |
| app/src/workflow/graph_orchestrator.py | Route ask_user to dialogue_specialist |
| app/src/workflow/workflow_runner.py | Thread management, resume capability |
| app/src/api.py | Add /resume endpoint |
| app/src/interface/ag_ui_schema.py | Add CLARIFICATION_REQUIRED event |

---

## Consequences

### Positive
- Clean separation between clarification (active) and default (passive) paths
- Database foundation enables future Codex memory system
- Checkpointing preserves context across user interactions
- Follows existing patterns (FacilitatorSpecialist for context, specialists for specific behaviors)

### Negative
- Adds infrastructure dependency (PostgreSQL)
- Another specialist to maintain
- Complexity in thread_id management across API calls

### Neutral
- default_responder_specialist remains unchanged (fallback-only)
- Existing FacilitatorSpecialist continues handling autonomous context gathering
