# ADR CORE-012: Web Builder ↔ Critic Subgraph (Generate-Critique-Refine Loop)

**Date:** 2025-01-13

**Status:** Implemented (Regression Fixed)

## Context

The web_builder specialist generates HTML/CSS/JS or Gradio Python applications. To ensure quality output, these artifacts should be reviewed by the critic_specialist before being presented to the user.

This creates a natural **generate-critique-refine loop**:
1. Router → web_builder (generates initial UI)
2. web_builder → critic_specialist (reviews UI)
3. critic decides: REVISE → web_builder (refine) OR ACCEPT → task complete

**Original Implementation (Pre-Regression):**
This loop was implemented as a **tight subgraph** with direct edges, bypassing the main router for efficiency.

**Regression (Discovered 2025-01-13):**
The subgraph architecture was partially dismantled, causing web_builder to route through the main router instead of directly to critic. This created unproductive loops and prevented the critique workflow from functioning.

## Problem Statement

**Without Direct Subgraph:**
```
Router → web_builder → check_task_completion → router
              ↓ (recommends critic)
         Router ignores recommendation
              ↓
         Routes back to web_builder
              ↓
         Unproductive loop detected after 3 cycles
```

**Why Router Routing Fails:**
1. **Inefficiency**: Every critique iteration requires 3 hops (web_builder → check_task_completion → router → critic) instead of 1 (web_builder → critic)
2. **Context Loss**: Router sees full conversation history but lacks context about the generate-critique workflow phase
3. **Recommendation Ambiguity**: Router treats web_builder's `recommended_specialists: ["critic_specialist"]` as an advisory suggestion, not a hard architectural requirement
4. **Loop Detection False Positives**: Valid refinement cycles (web_builder → systems_architect → web_builder) trigger loop detection when forced through router

## Solution: Direct Subgraph with Conditional Critique

Create a **bidirectional subgraph** that bypasses the main router for the generate-critique-refine loop.

### Architecture

```
                    ┌─────────────────────────┐
                    │   Router Specialist     │
                    └───────────┬─────────────┘
                                │
                                ▼
                    ┌─────────────────────────┐
                    │    web_builder          │ ◄─────┐
                    │  (generates UI)         │       │
                    └───────────┬─────────────┘       │
                                │ (direct edge)       │
                                ▼                     │
                    ┌─────────────────────────┐       │
                    │  critic_specialist      │       │
                    │  (reviews UI)           │       │
                    └───────────┬─────────────┘       │
                                │                     │
                    ┌───────────┴────────────┐        │
                    │ after_critique_decider │        │
                    └───────────┬────────────┘        │
                                │                     │
                    ┌───────────┴─────────┐           │
                    │                     │           │
              REVISE│                     │ACCEPT     │
                    ▼                     ▼           │
            ┌───────────────┐    ┌────────────────┐  │
            │  web_builder  │    │ check_task_    │  │
            │  (revision)   │────┤ completion     │  │
            └───────────────┘    └────────────────┘  │
                    │                     │           │
                    └─────────────────────┘───────────┘
                                          │
                                          ▼
                                   ┌──────────────┐
                                   │     END      │
                                   └──────────────┘
```

### Implementation

**1. Config (config.yaml)**
```yaml
critic_specialist:
  revision_target: "web_builder"  # ← CRITICAL: Defines REVISE destination
  requires_artifacts: ["ui_artifact"]
  artifact_providers:
    ui_artifact: "web_builder"
```

**2. Graph Wiring (graph_builder.py)**

**Step A: Exclude web_builder from hub-and-spoke routing**
```python
excluded_specialists = [
    router_name,
    CoreSpecialist.ARCHIVER.value,
    CoreSpecialist.END.value,
    CoreSpecialist.CRITIC.value,
    "web_builder"  # ← Part of web_builder ↔ critic subgraph
]
```

**Step B: Add direct edge web_builder → critic**
```python
if "web_builder" in self.specialists:
    workflow.add_edge("web_builder", CoreSpecialist.CRITIC.value)
    logger.info("Graph Edge: Added direct edge web_builder → critic_specialist")
```

**Step C: Critic conditional edge (already exists)**
```python
workflow.add_conditional_edges(
    CoreSpecialist.CRITIC.value,
    self.orchestrator.after_critique_decider,
    {
        revision_target: revision_target,  # REVISE → web_builder
        CoreSpecialist.END.value: CoreSpecialist.END.value,  # ACCEPT → end
        router_name: router_name  # Fallback
    }
)
```

**3. Decider Logic (graph_orchestrator.py)**
```python
def after_critique_decider(self, state: GraphState) -> str:
    decision = state.get("scratchpad", {}).get("critique_decision")
    revision_target = critic_config.get("revision_target", CoreSpecialist.ROUTER.value)

    if decision == "REVISE":
        return revision_target  # Direct to web_builder
    elif decision == "ACCEPT":
        return self.check_task_completion(state)  # Begin termination
    else:
        return CoreSpecialist.ROUTER.value  # Fallback
```

**4. Routing History Tracking (CRITICAL for Archive Reports)**

Specialists reached via direct edges MUST add themselves to `routing_history`:

```python
# web_builder.py
updated_state = {
    "messages": [ai_message],
    "artifacts": {"html_document.html": web_content.html_document},
    "recommended_specialists": ["critic_specialist"],
    "routing_history": [self.specialist_name]  # CRITICAL: Track subgraph execution
}

# critic_specialist.py
updated_state = {
    "messages": [ai_message],
    "artifacts": {"critique.md": critique_text},
    "scratchpad": {"critique_decision": critique.decision},
    "routing_history": [self.specialist_name]  # CRITICAL: Track subgraph execution
}
```

**Why This Matters:**
- `routing_history` uses `operator.add` annotation, so each specialist appends its name to the list
- The ArchiverSpecialist uses `routing_history` to generate workflow reports
- Without self-tracking, subgraph specialists are **invisible in archive reports**
- Multi-step critique cycles (`web_builder → critic → web_builder → critic → ...`) must be fully visible to users

**Router vs. Direct Edge Tracking:**
- Router automatically adds destinations to `routing_history` when routing
- Direct edges bypass the router, so specialists must track themselves
- This pattern applies to **all** subgraph specialists, not just web_builder ↔ critic

## Consequences

### Positive

1. **Eliminates Router Hops**: Generate-critique-refine loop is 66% faster (1 edge vs 3 edges per iteration)
2. **Prevents False Loop Detection**: Valid refinement cycles no longer trigger unproductive loop detection
3. **Architectural Clarity**: Subgraph is explicit in both code and config, making intent clear
4. **Scalable Pattern**: Can be replicated for other generate-critique workflows (e.g., code_generator ↔ code_reviewer)
5. **Recommendation-Agnostic**: Doesn't rely on router interpreting `recommended_specialists` correctly

### Negative

1. **Increased Coupling**: web_builder and critic_specialist are tightly coupled through direct edge
2. **Config Dependency**: `revision_target` MUST be configured correctly or subgraph breaks
3. **Router Bypass**: Router no longer has visibility into critique iterations (acceptable tradeoff)

### Trade-offs

**Why Not Use Router Recommendations?**
- ✅ **Tried**: web_builder sets `recommended_specialists: ["critic_specialist"]`
- ❌ **Failed**: Router treats recommendations as advisory, not mandatory
- ❌ **Result**: Router routes back to web_builder, creating loop
- ✅ **Alternative**: Direct edge enforces architectural intent without relying on LLM reasoning

## Testing

### Unit Tests
**graph_builder.py:**
- ✅ `test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_critic` - Verifies critic edges wired correctly
- ✅ All 10 graph_builder unit tests pass

**critic_specialist.py:**
- ✅ `test_critic_specialist_accepts_and_completes_task` - Verifies ACCEPT decision + routing_history tracking
- ✅ `test_critic_specialist_revises_and_recommends_target` - Verifies REVISE decision + routing_history tracking
- ✅ `test_critic_specialist_handles_strategy_failure` - Verifies error handling

**web_builder.py:**
- ✅ `test_web_builder_generates_html` - Verifies HTML generation + routing_history tracking
- ✅ All 5 web_builder unit tests pass

### Integration Tests (Needed)
- ⚠️ **TODO**: Add integration test verifying web_builder → critic → web_builder → critic → END flow
- ⚠️ **TODO**: Verify REVISE decision routes to web_builder (not router)
- ⚠️ **TODO**: Verify ACCEPT decision completes task successfully
- ⚠️ **TODO**: Verify routing_history in archive reports shows complete subgraph execution trace

## Regression Notes

**How This Was Lost:**
1. Original implementation existed but was undocumented
2. Architectural knowledge lost across LLM context windows
3. Code partially dismantled without understanding it was a cohesive pattern
4. web_builder reverted to hub-and-spoke routing

**Prevention:**
1. ✅ This ADR documents the pattern explicitly
2. ✅ Inline code comments explain exclusions
3. ✅ Config includes `revision_target` with explanatory comment
4. ⚠️ **TODO**: Update GRAPH_CONSTRUCTION_GUIDE.md with subgraph patterns
5. ⚠️ **TODO**: Add integration tests to catch regressions

## Related ADRs

- **ADR-CORE-002**: Self-Correction Signal (alternative approach using recommendations)
- **ADR-CORE-006**: Fail-Fast on Unknown Graph Routes (validates edge destinations)
- **ADR-CORE-CHAT-002**: Tiered Chat Subgraph (similar pattern: router → virtual coordinator → fanout)

## Future Enhancements

1. **Generalize Pattern**: Create reusable `add_critique_subgraph()` helper in GraphBuilder
2. **Multi-Artifact Critique**: Support critiquing multiple artifact types (code, data, images)
3. **Critique Strategy Configuration**: Allow runtime selection of critique strategy (LLM, rule-based, hybrid)
4. **Iteration Limits**: Add max critique cycles to prevent infinite refinement loops

## Example Usage

**User Request:**
> "Build me a dark-themed recipe app with ingredient tracking"

**Execution Flow:**
```
1. Router → web_builder
2. web_builder generates initial HTML
3. web_builder → critic_specialist (direct edge)
4. critic reviews: "Color contrast insufficient for dark theme" (REVISE)
5. critic → web_builder (via after_critique_decider)
6. web_builder refines colors
7. web_builder → critic_specialist (direct edge)
8. critic reviews: "Looks good!" (ACCEPT)
9. critic → check_task_completion → END
```

**Total Hops:** 9 edges
**Without Subgraph:** 15 edges (6 extra router hops)
**Efficiency Gain:** 40% reduction in graph traversal

---

**Signed-off-by:** Claude Code (ADR-CORE-012 documentation + regression fix)
**Reviewed-by:** Pending user review
**Implementation Commit:** `bb4507c` - "Restore web_builder ↔ critic subgraph (fix regression)"

---

## Supersession Note (2025-12-25)

**Issue:** [#7 - ARCH: Migrate systems_architect to MCP and refactor critique to ReActMixin pattern](https://github.com/shanevcantwell/langgraph-agentic-scaffold/issues/7)

The `web_builder` exclusion from hub-and-spoke routing has been **removed** from `critic_loop.py`.

**Rationale:**
- Excluding `web_builder` blocked direct routing when Triage correctly recommended it
- Triage now properly distinguishes "Build me X" (web_builder) from "Create a plan for X" (systems_architect)
- The exclusion created a routing dead-end: Triage recommends web_builder → Router rejects it → falls back to default_responder

**Migration Path:**
Per Issue #7, critique will move to **internal iteration via MCP** (Phase 2 pattern) rather than graph-level subgraph routing (Phase 1). The web_builder will call critic via MCP internally when needed, eliminating the need for subgraph exclusions.

**Current State:**
- `web_builder` is now directly routable via hub-and-spoke
- Critique subgraph edges still exist but web_builder can also be reached directly
- Full MCP migration pending per Issue #7

---

## Removal Note (2026-02-12, Issue #161)

**The critic subgraph described in this ADR has been entirely removed.**

Issue [#161](https://github.com/shanevcantwell/langgraph-agentic-scaffold/issues/161) deleted `CriticLoopSubgraph`, `CriticSpecialist`, and all critique strategies. Net change: -759 lines across 6 commits. Unit tests: 839 pass post-removal.

`web_builder` is now a standard hub-and-spoke specialist that flows through `classify_interrupt` → Exit Interview for completion evaluation, like all other specialists. The generate-critique-refine loop pattern described in this ADR no longer exists in the codebase.

**Why removed (not migrated to MCP as Issue #7 envisioned):**
- The critic subgraph's `add_conditional_edges()` calls created parallel branch leaks (#160) — `add_conditional_edges` is additive in LangGraph, meaning multiple calls for the same source node create parallel branches rather than overwriting
- Subgraph-managed nodes (`web_builder`, `critic_specialist`) needed exclusion from the hub-and-spoke loop via `get_excluded_specialists()`, but this created routing dead-ends when Triage correctly recommended `web_builder`
- Ghost node bug: `_check_stabilization_action` returned `error_handling_specialist` which didn't exist as a graph node, crashing circuit breaker recovery
- The Exit Interview pattern (already used by all other specialists) provides sufficient quality evaluation without dedicated critic infrastructure

**Commits:** `bc8afa8`, `1e0eec4`, `38628c7`, `cba5ef4`, `e40c7b1`

This ADR is retained as historical record of the pattern and the lessons learned from its removal.
