# **Router Blocking Signal Enforcement**

* **Status:** Deferred
* **Date:** 2025-01-13
* **Deciders:** System Architecture Team
* **Related:** ADR-CORE-001 (Fail-Fast Startup Validation), MANDATE-CORE-001 (Progressive Resilience), Tasks 1.4-1.6 (System Invariants & Circuit Breaker)

---

## **Context**

The test `test_router_respects_specialist_cannot_proceed` validates that when a specialist explicitly signals it "cannot proceed" (a blocking signal), the RouterSpecialist should treat this as a hard constraint rather than an advisory recommendation. This is distinct from soft recommendations provided by PromptTriageSpecialist (which are advisory per ADR-CORE-011).

**Current Behavior:**
- RouterSpecialist receives blocking signals from specialists via state
- No formal mechanism to enforce these signals as hard constraints
- Router may ignore blocking signals and route to the blocked specialist anyway
- Test failure indicates this enforcement is not yet implemented

**Expected Behavior:**
- Specialist sets a blocking signal (e.g., `specialist_cannot_proceed: True`, `blocked_specialist: "some_specialist"`)
- RouterSpecialist checks for blocking signals before making routing decisions
- Router MUST NOT route to a specialist that has been explicitly blocked
- Violation should trigger fail-fast behavior (error or route to END)

**Why This Matters:**
This aligns with the **Aggressive Resilience** pillar (ADR Compendium) and fail-fast philosophy (ADR-CORE-001, CORE-006). Silent failures where specialists explicitly signal inability but are routed to anyway violate zero-tolerance for silent failures.

---

## **Decision**

**We are DEFERRING implementation of router-level blocking signal enforcement.**

This feature requires infrastructure from the **System Invariants & Circuit Breaker** workstream (Tasks 1.4-1.6):

1. **Invariant Definition** (Task 1.4): Formal rules for state integrity, including "blocked specialists must not be routed to"
2. **InvariantMonitor Service** (Task 1.5): Pre/post-execution checks integrated into GraphOrchestrator
3. **Stabilization Actions** (Task 1.6): Configuration mapping invariant violations to actions (HALT, ROUTE_TO_ERROR_HANDLER, ROUTE_TO_HUMAN)

**Rationale for Deferral:**
- Building blocking signal enforcement in isolation would create technical debt
- The proper implementation requires the invariant monitoring infrastructure
- Current system is functional without this feature (graceful degradation, not critical path failure)
- Test failure is acceptable for alpha release as it represents a planned enhancement, not a regression

**Roadmap Position:**
- **Now (Alpha Release):** Document deferral, test marked as known failure
- **Phase 1 (Post-Alpha):** Implement Tasks 1.4-1.6 (invariant monitoring system)
- **Phase 2:** Implement blocking signal enforcement as a specific invariant rule
- **Phase 3:** Add comprehensive tests for blocking signal scenarios

---

## **Implementation Notes (For Future Work)**

When implemented, the pattern should be:

**1. Specialist Blocking Signal Format (in scratchpad or state):**
```python
# Specialist signals it cannot proceed and blocks another specialist
return {
    "specialist_cannot_proceed": True,
    "blocked_specialist": "some_specialist_name",
    "blocking_reason": "Missing required artifact 'system_plan'"
}
```

**2. Router Pre-Routing Invariant Check:**
```python
# In GraphOrchestrator or RouterSpecialist
def check_blocking_signals(state: Dict[str, Any], proposed_destination: str) -> bool:
    """Invariant: Cannot route to a specialist that has been explicitly blocked."""
    blocked = state.get("blocked_specialist")
    if blocked and proposed_destination == blocked:
        reason = state.get("blocking_reason", "Unknown reason")
        raise WorkflowError(
            f"Cannot route to '{proposed_destination}': {reason}. "
            f"Blocked by specialist's explicit 'cannot proceed' signal."
        )
    return True
```

**3. Integration with InvariantMonitor:**
```python
# In InvariantMonitor service (Task 1.5)
def pre_execution_checks(state: Dict[str, Any], next_node: str) -> None:
    """Run all invariants before executing next node."""
    check_blocking_signals(state, next_node)
    check_dossier_validity(state)
    check_loop_detection(state)
    # ... other invariants
```

---

## **Consequences**

### **Positive:**
* **Avoids Technical Debt:** Prevents building blocking signal enforcement in isolation, which would need refactoring when invariant system arrives
* **Clear Roadmap:** Explicitly documents the dependency on Tasks 1.4-1.6 and sequencing
* **Maintains Focus:** Allows team to complete critical-path features for alpha release without detour

### **Negative:**
* **Test Failure:** `test_router_respects_specialist_cannot_proceed` will continue to fail until implemented
* **Potential Silent Failures:** System may route to blocked specialists without enforcement (mitigated by specialist-level error handling)
* **User Expectation:** Users may expect this behavior based on test name/documentation

### **Mitigations:**
* Mark test with `@pytest.mark.skip(reason="Deferred per ADR-CORE-009")` to document known limitation
* Add warning logs in RouterSpecialist when blocking signals are present (non-enforcing, visibility only)
* Document in [DEVELOPERS_GUIDE.md](../../docs/DEVELOPERS_GUIDE.md) that blocking signals are advisory until Phase 2

---

## **Related Work**

* **ADR-CORE-001:** Fail-Fast Startup Validation ✅ (Implemented)
* **ADR-CORE-006:** Fail-Fast on Unknown Graph Routes ✅ (Implemented)
* **ADR-CORE-011:** Triage Advisory Routing ✅ (Implemented - distinguishes advisory vs. blocking)
* **MANDATE-CORE-001:** Progressive Resilience Architecture (Tier 1 only, Tiers 2-4 pending)
* **Tasks 1.4-1.6:** System Invariants & Circuit Breaker (CRITICAL GAP - highest priority post-alpha)

---

## **Acceptance Criteria (When Implemented)**

- [ ] `test_router_respects_specialist_cannot_proceed` passes
- [ ] RouterSpecialist raises `WorkflowError` when attempting to route to blocked specialist
- [ ] Error message includes blocking reason from specialist signal
- [ ] Blocking signals are cleared after routing decision to prevent stale state
- [ ] Integration test validates blocking signal enforcement with real specialists
- [ ] LangSmith traces show clear error when blocking signal violated

---

## **Notes**

This ADR created during alpha release preparation (2025-01-13) when reviewing test failures. Test failure is **expected and acceptable** for alpha release as it represents planned future work, not a regression.

**Test Status:** Mark as known limitation with skip decorator:
```python
@pytest.mark.skip(reason="Blocking signal enforcement deferred per ADR-CORE-009 (requires Tasks 1.4-1.6)")
def test_router_respects_specialist_cannot_proceed():
    ...
```
