# ADR CORE-011: Triage Advisory Routing

**Date:** 2025-01-13

**Status:** Implemented

## Context

The `PromptTriageSpecialist` was originally designed to perform a pre-flight analysis of user prompts and recommend specialist(s) to handle the request. The `RouterSpecialist` consumed these recommendations by **filtering** its available specialists to ONLY those recommended by triage.

This **restrictive** behavior created a critical failure mode discovered during alpha testing:

1. User submits prompt: "Rewrite this Gradio app in [attached code]"
2. Triage analyzes prompt and recommends: `["text_analysis_specialist"]`
3. Router receives ONLY text_analysis_specialist as available choice
4. Router (correctly) determines web_builder is needed, but it's filtered out
5. Router validation fails → falls back to `default_responder_specialist`
6. default_responder generates inappropriate code response

**Root Cause:** Triage's incomplete understanding of the request (didn't recognize attached code as web UI) blocked the router from making the correct decision, even though the router had access to full conversation context including file attachments.

## Problem Statement

**Restrictive triage creates single point of failure:** A triage error blocks correct routing decisions, causing workflow failures even when the router could make the right choice.

**Design Tension:**
- Triage sees only the initial prompt (lightweight, fast analysis)
- Router sees full conversation context (messages, attachments, state)
- Yet the less-informed specialist constrains the more-informed one

This violates the principle of "progressive information refinement" - later stages should be able to override earlier stages when they have better information.

## Solution

Transform triage from **restrictive filter** to **advisory suggestion**.

### Implementation Changes

**1. RouterSpecialist._get_available_specialists() (router_specialist.py:35-43)**

Before (Restrictive):
```python
def _get_available_specialists(self, state: Dict[str, Any]) -> Dict[str, Dict]:
    """Determines the list of specialists available for routing in the current turn."""
    recommended_specialists = state.get("recommended_specialists")
    if recommended_specialists:
        available = {name: self.specialist_map[name] for name in recommended_specialists if name in self.specialist_map}
        logger.info(f"Filtering router choices based on Triage recommendations: {list(available.keys())}")
        return available  # ← BLOCKS other specialists
    return self.specialist_map
```

After (Advisory):
```python
def _get_available_specialists(self, state: Dict[str, Any]) -> Dict[str, Dict]:
    """Returns the full list of specialists available for routing.

    NOTE: This always returns the COMPLETE specialist map. Triage recommendations
    are provided as advisory context in the LLM prompt (see _get_llm_choice),
    but do NOT restrict the router's choices. This prevents triage errors from
    blocking correct routing decisions.
    """
    return self.specialist_map  # ← Always return full list
```

**2. RouterSpecialist._get_llm_choice() (router_specialist.py:66-100)**

Added advisory context injection:
```python
# Check for triage recommendations (advisory, not restrictive)
recommended_specialists = state.get("recommended_specialists")
triage_advisory = ""
if recommended_specialists:
    triage_advisory = f"\n\n**TRIAGE SUGGESTIONS (ADVISORY, NOT MANDATORY)**:\nThe triage specialist recommends considering these specialists: {', '.join(recommended_specialists)}.\nThese are suggestions based on initial analysis. You may choose a different specialist if you have stronger reasoning."
    logger.info(f"Triage provided advisory recommendations: {recommended_specialists}")

contextual_prompt_addition = f"Based on the current context, you MUST choose a specialist from the following list:\n{tools_list_str}{triage_advisory}"
```

**Key Changes:**
- Router always sees ALL specialists (no filtering)
- Triage recommendations appear as context in LLM prompt
- Router explicitly told triage is "ADVISORY, NOT MANDATORY"
- Router can override triage when it has better reasoning

**3. Test Updates (test_router_specialist.py:33-53)**

Updated `test_get_available_specialists_with_recommendations` to verify advisory behavior:
```python
def test_get_available_specialists_with_recommendations(router_specialist):
    """Tests that the specialist list is NOT filtered by recommendations (advisory mode).

    As of ADR-CORE-011, triage recommendations are advisory, not restrictive.
    The router always receives the full specialist list, with recommendations
    provided as context in the LLM prompt (see _get_llm_choice).
    """
    # ...
    # Assert: ALL specialists are available, regardless of recommendations
    assert len(available) == 3  # All 3 specialists present
```

## Consequences

### Positive

1. **Eliminates Single Point of Failure:** Triage errors no longer block correct routing decisions
2. **Progressive Information Refinement:** Router (with full context) can override triage (prompt-only analysis)
3. **Graceful Degradation:** System continues working correctly even when triage makes mistakes
4. **Preserves Triage Value:** Recommendations still guide router's decision, improving efficiency when correct
5. **Better User Experience:** File upload scenarios (like "rewrite this Gradio app") now route correctly

### Negative

1. **Increased Router LLM Context:** Router prompt now includes triage suggestions + full specialist list (minor token increase)
2. **Potential Over-Reliance:** Router might occasionally ignore good triage advice (mitigated by clear prompt instructions)

### Testing

All tests pass after implementation:
- ✅ 8/8 router unit tests (including updated advisory test)
- ✅ 7/7 API unit tests
- ✅ 3/3 API streaming integration tests

### Related Issues Fixed

This change resolves the file attachment routing issue documented in `FILE_ATTACHMENT_INVESTIGATION.md`:
- **Issue:** web_builder blocked by triage → falls back to default_responder → generates code
- **Resolution:** Router can now select web_builder even when triage doesn't recommend it

## Future Considerations

**Hybrid Routing (ADR-CORE-005, CORE-007):**
This advisory pattern aligns with the planned hybrid routing architecture:
- Reflexive Routing: Deterministic pattern matching (bypasses LLM entirely)
- Advisory Triage: Lightweight prompt analysis (suggestions only)
- Main Router: Final decision with full context (authoritative)
- Ranked Fallback: Fallback plans when primary routing fails

**Triage Evolution:**
Future enhancements could make triage smarter without reintroducing restrictive behavior:
- Multi-turn triage: Update recommendations as conversation evolves
- Confidence scores: Router weighs triage suggestions by confidence
- Negative recommendations: "Definitely NOT these specialists" (still advisory)

## Implementation Notes

**Deployment Safety:**
- Backward compatible: No state schema changes
- Zero downtime: Old behavior → new behavior is seamless
- Rollback safe: Can revert to restrictive mode if needed (not recommended)

**Observability:**
LangSmith traces will show:
1. Triage recommendations in `recommended_specialists` state field
2. Router receiving full specialist list
3. Router prompt containing advisory context
4. Router's final choice (which may differ from triage)

This provides full visibility into when/why router overrides triage.

---

**Signed-off-by:** Claude Code (ADR-CORE-011 implementation)
**Reviewed-by:** Pending user review
