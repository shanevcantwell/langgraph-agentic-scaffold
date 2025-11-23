# ADR: Triage Specialist Recommendations for Routing Guidance

**Status:** Accepted
**Date:** 2025-01-23
**Related:** ARCHITECTURE.md Section 2.2, ADR-CORE-016 (Menu Filter Pattern)

## Context

After the Triage → TriageArchitect refactoring (likely during Gemini 3.0 migration), the system lost the ability for triage to recommend specialists to the router. This caused the router to make blind choices from 15+ specialists after context gathering, leading to poor routing decisions and unproductive loops.

**Observed Issue:**
```
User: "Research winter weather in Colorado"
├─ Triage: ❌ No recommendations set (field removed from ContextPlan)
├─ Facilitator: Gathers context
└─ Router: Blind choice → text_analysis_specialist × 3 → LOOP DETECTED
```

## Decision

Restore the `recommended_specialists` field to the `ContextPlan` schema and implement an **advisory routing guidance pattern** where:

1. **TriageArchitect** analyzes the user request and recommends 1-3 specialists based on task type
2. **Recommendations flow through scratchpad** (`scratchpad.recommended_specialists`)
3. **Router receives guidance** but retains autonomy to override with stronger reasoning
4. **Distinction between advisory vs. dependency**:
   - Triage recommendations = Advisory (guidance only)
   - Failed specialist recommendations = Dependency (hard requirement)

## Implementation

### Schema Changes

**ContextPlan** (`app/src/interface/context_schema.py`):
```python
class ContextPlan(BaseModel):
    actions: List[ContextAction] = Field(default_factory=list)
    reasoning: str = Field(...)
    recommended_specialists: List[str] = Field(
        default_factory=list,  # ✅ Restored field
        description="Specialists recommended after context gathering"
    )
```

### Component Changes

**TriageArchitect** (`app/src/specialists/triage_architect.py`):
- Populates `scratchpad.recommended_specialists` from ContextPlan
- Prompt updated with common specialist descriptions and examples

**RouterSpecialist** (`app/src/specialists/router_specialist.py`):
- Filters recommendations against available menu (post-context-gathering)
- Distinguishes advisory (triage) vs. dependency (failed specialist) recommendations
- Planning specialists (`triage_architect`, `facilitator_specialist`) excluded from dependency detection

## Consequences

### Positive

✅ **Dramatically improved routing accuracy**: Router now receives task-appropriate guidance
✅ **Prevents unproductive loops**: Correct specialist chosen on first try
✅ **Preserves router autonomy**: Advisory pattern allows override with better reasoning
✅ **Clear separation of concerns**: Triage = analysis, Router = decision
✅ **Backward compatible**: Empty recommendations list is default (no breaking changes)

### Negative

⚠️ **Increased prompt complexity**: Triage prompt now includes specialist recommendations section
⚠️ **Cognitive load on small models**: Open-weight models must understand specialist types
⚠️ **Maintenance overhead**: Specialist list in triage prompt must stay synchronized with config

### Mitigations

- Triage prompt uses common specialist descriptions (not exhaustive list)
- Recommendations are optional (default empty list)
- Router can ignore recommendations if analysis suggests better choice
- Tests ensure backward compatibility with empty recommendations

## Testing

**Test Coverage:**
- 7 tests: ContextPlan schema validation
- 4 tests: TriageArchitect recommendation population
- 2 tests: RouterSpecialist recommendation filtering
- 1 test: End-to-end regression test for original issue

**Total:** 14 new tests + 12 existing router tests = **26 tests** covering this pattern

## Alternatives Considered

### Alternative 1: Mandatory Routing (Rejected)
**Approach:** Make triage recommendations mandatory (router must follow)
**Rejected Because:**
- Removes router's ability to reason about context-specific edge cases
- Creates rigid system unable to adapt to unexpected scenarios
- Advisory pattern preserves flexibility while providing guidance

### Alternative 2: Router-Only Reasoning (Current Before Fix)
**Approach:** Router makes all decisions without triage guidance
**Rejected Because:**
- Router sees 15+ specialists after context gathering
- No task-type hints available (generic specialist descriptions only)
- Results in poor choices and unproductive loops (observed in production)

### Alternative 3: Separate Recommendation Specialist
**Approach:** Create dedicated RecommendationSpecialist after facilitator
**Rejected Because:**
- Adds unnecessary complexity (extra graph node)
- Triage already analyzes task type for context gathering
- Natural to combine analysis + recommendation in single specialist

## References

- **Implementation:** `app/src/interface/context_schema.py:20-23`
- **Tests:** `app/tests/interface/test_context_schema.py`
- **Documentation:** `docs/ARCHITECTURE.md` Section 2.2
- **Related ADRs:** ADR-CORE-016 (Menu Filter Pattern for context-aware routing)

## Migration Notes

**For Existing Systems:**
1. ContextPlan schema change is additive (default empty list)
2. Existing triage prompts will work but won't provide recommendations
3. Update triage prompt to include specialist recommendations section
4. Test with live LLM to verify prompt changes produce valid recommendations

**Rollback Plan:**
If this pattern causes issues, the fix can be safely reverted by:
1. Removing `recommended_specialists` from ContextPlan (falls back to empty list default)
2. Router will continue working without recommendations (pre-fix behavior)
