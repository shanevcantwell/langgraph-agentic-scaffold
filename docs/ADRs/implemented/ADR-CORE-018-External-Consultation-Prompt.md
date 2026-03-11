# ADR-CORE-018: HitL Clarification Flow

**This plan file has been superseded by the formal ADR.**

See: [docs/ADR/ADR-CORE-018-HitL-Clarification-Flow.md](../../../docs/ADR/ADR-CORE-018-HitL-Clarification-Flow.md)

---

## External Consultation Prompt

The following prompt is designed to be shared with other LLMs to gather perspectives on the architectural design:

---

### PROMPT: LangGraph Agent Clarification Architecture Review

**Context**: Shopping this architectural question to frontier models (Gemini 3.0 Pro, Opus 4.5) for substantive critique before implementation. Full architecture docs attached.

I'm building a LangGraph-based agentic system and need architectural guidance on implementing a **Human-in-the-Loop (HitL) clarification flow**. Looking for critique, pattern recommendations, and alternative approaches I may have missed.

#### Current Architecture Context

The system uses a **Context Engineering** phase before the main routing loop:

```
User Request
    ↓
TriageArchitect (analyzes request, creates ContextPlan)
    ├─ actions: [RESEARCH, READ_FILE, LIST_DIRECTORY, SUMMARIZE, ASK_USER]
    └─ recommended_specialists: ["researcher_specialist", "chat_specialist"]
    ↓
FacilitatorSpecialist (executes actions via MCP, gathers context)
    ↓
RouterSpecialist (receives recommendations, makes final routing decision)
```

**Key Components:**

1. **ContextPlan Schema**: Contains `actions` (what context to gather) and `recommended_specialists` (routing hints)
2. **ContextAction Types**: RESEARCH (web search), READ_FILE, LIST_DIRECTORY, SUMMARIZE, **ASK_USER**
3. **FacilitatorSpecialist**: Executes autonomous context gathering via MCP (internal service calls)
4. **MCP (Message-Centric Protocol)**: Synchronous Python function calls between specialists

**The Gap:**
The `ASK_USER` action type exists in the schema but is **unhandled**. When TriageArchitect determines the request is ambiguous, it can produce a ContextPlan with only `ask_user` actions, but there's no specialist to present these questions to the user.

#### Proposed Solution

**Option A: Extend FacilitatorSpecialist**
- Add `ASK_USER` handling to FacilitatorSpecialist alongside other action types
- Facilitator already iterates through `context_plan.actions`
- Would format questions and return them, setting `clarification_required: True`
- Pro: No new specialist, uses existing pattern
- Con: Mixes autonomous gathering (deterministic) with user interaction (blocking)

**Option B: New DialogueSpecialist**
- Create dedicated specialist for presenting clarification questions
- Routing: When ContextPlan has ONLY `ask_user` actions, route to DialogueSpecialist
- DialogueSpecialist reads questions from `context_plan.actions`, formats with context, presents to user
- Pro: Clean separation of concerns (autonomous vs interactive)
- Con: Another specialist to maintain, more routing complexity

**Option C: Hybrid - ContextGatheringSpecialist**
- New specialist that handles BOTH autonomous gathering AND user questions
- Would replace FacilitatorSpecialist entirely
- Pro: Single specialist for all context-related work
- Con: Larger specialist, harder to test, mixes concerns

#### Additional Context: LangGraph Checkpointing

For HitL to work, we need state persistence when waiting for user input:
- Plan to use `PostgresSaver` from `langgraph-checkpoint-postgres`
- `interrupt_before=["dialogue_specialist"]` to pause graph execution
- Thread-based conversation resumption via `/resume` endpoint

#### Specific Questions

1. **Separation of Concerns**: Should context gathering (autonomous, via MCP) and clarification (interactive, requires HitL) be in the same specialist?

2. **State Flow**: Currently `gathered_context` is injected into downstream specialists via `_get_enriched_messages()`. Should clarification questions receive the same enrichment, or is that overkill?

3. **Partial Context Gathering**: What if ContextPlan has BOTH autonomous actions AND `ask_user`? Should we:
   - Execute autonomous first, then present questions with gathered context
   - Present questions first, then gather after clarification
   - Interleave (seems complex)

4. **Graph Topology**: Given we use a hub-and-spoke pattern with RouterSpecialist at center, where should DialogueSpecialist sit?
   - After TriageArchitect (short-circuit before Router)?
   - After Router like other specialists?
   - Parallel to Facilitator?

#### Related Pattern: "The Fishbowl" (ADR-CORE-017)

There's an existing pattern in the codebase called "The Fishbowl" - an ephemeral discussion buffer for multi-model consensus. It introduces:
- `dialogue_buffer` - stores back-and-forth debate between Alpha/Bravo progenitors
- `dialogue_phase` - controls mode: "opening", "rebuttal", "synthesis", "human_intervention"
- `DiscussionConductorSpecialist` - orchestrates the debate cycle

This creates THREE context-like patterns emerging:

| Pattern | Source | Storage | Purpose |
|---------|--------|---------|---------|
| **Gathered Context** | FacilitatorSpecialist via MCP | `artifacts.gathered_context` | Autonomous context gathering |
| **Dialogue Buffer** | Fishbowl/Progenitors | `dialogue_buffer` (ephemeral) | Debate between specialists |
| **Clarification Context** | HitL/User | ? | Interactive context from user |

All three need to stay out of `messages` (permanent history) but be available to downstream specialists. This suggests a potential **unified context layer** architecture.

**Question for external consultation:** Should we unify these patterns into a single Context abstraction, or keep them separate (each with its own state field and specialist)?

#### Relevant Documentation

**Architecture docs that may be helpful:**
- The system uses 3 state layers: `messages` (permanent), `artifacts` (structured outputs), `scratchpad` (transient signals)
- Parallel specialists write ONLY to `artifacts`, join nodes write to `messages`
- MCP provides synchronous service calls between specialists without going through the graph

**Current FacilitatorSpecialist pattern:**
```python
def _execute_logic(self, state: dict) -> Dict[str, Any]:
    context_plan = artifacts.get("context_plan")
    gathered_context = []

    for action in context_plan.actions:
        if action.type == ContextActionType.RESEARCH:
            results = self.mcp_client.call("researcher_specialist", "search", query=action.target)
            gathered_context.append(f"### Research: {action.target}\n{results}")
        elif action.type == ContextActionType.READ_FILE:
            content = self.mcp_client.call("file_specialist", "read_file", path=action.target)
            gathered_context.append(f"### File: {action.target}\n{content}")
        # ... other action types
        # ASK_USER: NOT YET IMPLEMENTED

    return {"artifacts": {"gathered_context": "\n\n".join(gathered_context)}}
```

#### What I'm Looking For

1. **Architecture critique**: Do any of the options have fundamental flaws I'm missing?
2. **Pattern recommendations**: Have you seen similar HitL clarification patterns in agentic systems?
3. **State management considerations**: Any gotchas with LangGraph checkpointing for this use case?
4. **Alternative approaches**: Is there a better architecture I haven't considered?

---

## Documentation Status

**Docs/Code Discrepancy Found:**
- `docs/ARCHITECTURE.md` (Nov 23) says: ASK_USER → `end_specialist`
- `docs/GRAPH_VISUALIZATIONS.md` (Nov 23) says: ASK_USER → `END_SPEC[End Specialist]`
- `app/src/workflow/graph_orchestrator.py` (Nov 26) says: → `"default_responder"` (broken name)

The code is newer than the docs. Either:
1. Code is wrong (should match docs and route to end_specialist)
2. Code represents a new direction toward dedicated DialogueSpecialist (but has wrong node name)

**Recommendation:** Resolve this discrepancy as part of implementation. The docs describe the original intent; the code change suggests someone started down the DialogueSpecialist path but didn't complete it.
