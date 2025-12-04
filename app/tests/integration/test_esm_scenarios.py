# app/tests/integration/test_esm_scenarios.py
"""
Integration tests for Emergent State Machine (ESM) scenarios.

These tests verify that LAS can handle tasks requiring state machine behavior:
- Phase tracking and transitions
- Backtracking on dead ends
- Progress persistence across specialist handoffs
- Exhaustion tracking (don't retry failed paths)

ESM Design Philosophy:
- Provide state machine primitives to the model
- Let the model discover when to use them
- These tests validate the capability exists, not that the model always uses it

Test Categories:
1. Research with exhaustion tracking
2. Iterative refinement with rollback
3. Approval workflows with explicit states
4. Hypothesis elimination (debugging)
5. Constraint satisfaction with backtracking
"""
import pytest
from fastapi.testclient import TestClient
from typing import List, Dict, Any


# ============================================================================
# TEST 1: Research with Exhaustion Tracking
# ============================================================================

@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired to specialist prompts. Tests document expected behavior.")
def test_research_exhaustion_tracking(initialized_app):
    """
    ESM Scenario: Research with source exhaustion tracking.

    Prompt: "Research the breeding history of the Olde Boston Bulldogge.
    Track which sources you've tried. If a source yields nothing, mark it
    exhausted and don't retry. If all primary sources are exhausted, pivot
    to secondary analysis."

    Expected ESM Behavior:
    - State: PRIMARY_SEARCH → PRIMARY_EXHAUSTED → SECONDARY_ANALYSIS → COMPLETE
    - Artifacts should show exhausted sources
    - No repeated searches on same source
    - Final response acknowledges source limitations

    This is the actual failure case from the research bug investigation.
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": (
                "Research the breeding history of the Olde Boston Bulldogge. "
                "Track which sources you've tried. If a source yields nothing, "
                "mark it exhausted and don't retry. If all primary sources are "
                "exhausted, pivot to secondary analysis."
            ),
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # CRITICAL: No loop detection (would indicate ESM failure)
        scratchpad = final_state.get("scratchpad", {})
        assert scratchpad.get("termination_reason") is None, (
            f"Workflow should not be halted by loop detection. "
            f"Termination reason: {scratchpad.get('termination_reason')}"
        )

        # ESM Evidence: Check for state tracking artifacts
        artifacts = final_state.get("artifacts", {})

        # Expected: Some form of exhaustion tracking
        # Could be: exhausted_sources, search_state, esm_state, etc.
        esm_artifacts = [
            k for k in artifacts.keys()
            if any(term in k.lower() for term in ["exhausted", "state", "tried", "phase"])
        ]

        # ESM Evidence: Routing history should show pivot behavior
        routing_history = final_state.get("routing_history", [])

        # Should NOT see web_specialist repeatedly without state change
        web_specialist_count = routing_history.count("web_specialist")
        researcher_count = routing_history.count("researcher_specialist")

        # If web_specialist was called multiple times, there should be
        # evidence of different queries or state transitions between calls
        if web_specialist_count > 2:
            # Check for state progression in scratchpad
            assert esm_artifacts or "gathered_context" in artifacts, (
                f"Multiple web_specialist calls without ESM state tracking. "
                f"Routing history: {routing_history}"
            )

        # Verify workflow completed successfully
        assert final_state.get("error_report") is None


@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Stub test for future capability.")
def test_research_no_retry_exhausted_sources(initialized_app):
    """
    Negative test: Verify ESM prevents retry of exhausted sources.

    Setup: Pre-populate state with exhausted sources
    Expected: System should NOT retry those sources

    This tests the "don't retry" constraint of ESM.
    """
    app = initialized_app

    # This test requires ability to inject initial state
    # For now, stub out the structure
    pytest.skip("Requires state injection capability - stub for architecture validation")


# ============================================================================
# TEST 2: Iterative Refinement with Rollback
# ============================================================================

@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Tests document expected behavior.")
def test_iterative_refinement_with_rollback(initialized_app):
    """
    ESM Scenario: Database schema design with constraint validation and rollback.

    Prompt: "Design a database schema for a multi-tenant SaaS. After drafting,
    validate against these 5 constraints: [1] tenant isolation, [2] audit logging,
    [3] soft deletes, [4] timestamp tracking, [5] referential integrity.
    If validation fails, identify which design decision caused it and roll back
    to that decision point, not to the beginning."

    Expected ESM Behavior:
    - State: DRAFT → VALIDATE → (ROLLBACK_TO_DECISION_N | COMPLETE)
    - Artifacts should show decision tree
    - Rollback should be targeted, not full restart
    - Final schema satisfies all constraints
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": (
                "Design a database schema for a multi-tenant SaaS application. "
                "After drafting, validate against these 5 constraints: "
                "[1] tenant isolation (no cross-tenant data leakage), "
                "[2] audit logging (all changes tracked), "
                "[3] soft deletes (no hard deletes), "
                "[4] timestamp tracking (created_at, updated_at on all tables), "
                "[5] referential integrity (all foreign keys valid). "
                "If validation fails, identify which design decision caused it "
                "and roll back to that decision point, not to the beginning."
            ),
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # ESM Evidence: Check for decision tracking
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Expected: Decision tree or checkpoint artifacts
        decision_artifacts = [
            k for k in artifacts.keys()
            if any(term in k.lower() for term in ["decision", "checkpoint", "rollback", "phase"])
        ]

        # ESM Evidence: Validation results should be tracked
        validation_artifacts = [
            k for k in artifacts.keys()
            if any(term in k.lower() for term in ["validation", "constraint", "check"])
        ]

        # Verify no unproductive loops
        routing_history = final_state.get("routing_history", [])
        _assert_no_unproductive_loops(routing_history)

        # Verify workflow completed
        assert final_state.get("error_report") is None


@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Stub test for targeted rollback.")
def test_rollback_targets_specific_decision(initialized_app):
    """
    Granular test: Verify rollback targets the specific failing decision.

    This tests the core ESM capability of targeted backtracking rather than
    naive restart-from-scratch behavior.
    """
    pytest.skip("Requires decision tree inspection - stub for architecture validation")


# ============================================================================
# TEST 3: Approval Workflow with Explicit States
# ============================================================================

@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Tests document expected behavior.")
def test_approval_workflow_state_machine(initialized_app):
    """
    ESM Scenario: Press release with review cycles and escalation.

    Prompt: "Draft a press release. Submit for review. If rejected, incorporate
    feedback and resubmit. Track revision count. After 3 rejections, escalate
    to human with summary of blocking issues."

    Expected ESM Behavior:
    - State Machine: DRAFT → PENDING_REVIEW → (REVISION_N | APPROVED | ESCALATED)
    - Revision counter tracked in state
    - Escalation triggered at threshold
    - Human handoff with issue summary

    Note: This test may require HitL integration or mock reviewer.
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": (
                "Draft a press release announcing a new AI safety feature. "
                "The release should be professional and highlight key benefits. "
                "Submit for review. If rejected, incorporate feedback and resubmit. "
                "Track revision count. After 3 rejections, escalate to human "
                "with summary of blocking issues."
            ),
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # ESM Evidence: Check for revision tracking
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Expected: Revision counter or state marker
        state_markers = [
            k for k in {**artifacts, **scratchpad}.keys()
            if any(term in k.lower() for term in ["revision", "review", "state", "count", "draft"])
        ]

        # Verify workflow terminated appropriately
        # (Either completed successfully or escalated to human)
        routing_history = final_state.get("routing_history", [])

        # Should NOT loop indefinitely
        assert len(routing_history) < 20, (
            f"Workflow ran too many iterations without completing. "
            f"History length: {len(routing_history)}"
        )


@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="Requires HitL integration. Stub for escalation behavior.")
def test_approval_escalates_after_threshold(initialized_app):
    """
    Test that approval workflow correctly escalates after N rejections.

    Requires:
    - Mock reviewer that always rejects
    - HitL checkpoint capability
    - Escalation detection
    """
    pytest.skip("Requires HitL integration - stub for architecture validation")


# ============================================================================
# TEST 4: Hypothesis Elimination (Debugging)
# ============================================================================

@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Tests document expected behavior.")
def test_hypothesis_elimination_debugging(initialized_app):
    """
    ESM Scenario: Debugging with hypothesis tracking.

    Prompt: "Debug why the build is failing. Form 3 hypotheses. Test each.
    Mark eliminated hypotheses. If all eliminated, form new hypotheses based
    on what you learned. Don't re-test eliminated paths."

    Expected ESM Behavior:
    - State: HYPOTHESIZE → TEST_H1 → (ELIMINATE_H1 | CONFIRM_H1) → ...
    - Hypotheses tracked with status (untested, eliminated, confirmed)
    - No re-testing of eliminated hypotheses
    - New hypotheses informed by prior eliminations
    """
    app = initialized_app

    # Provide a "failing build" artifact for the system to debug
    build_error = """
    ERROR: ModuleNotFoundError: No module named 'pandas'

    Traceback:
      File "app.py", line 5, in <module>
        import pandas as pd
      File "analysis.py", line 12, in process_data
        df = pd.DataFrame(data)

    Build failed with exit code 1
    """

    with TestClient(app) as client:
        payload = {
            "input_prompt": (
                "Debug why this build is failing. Form 3 hypotheses. Test each. "
                "Mark eliminated hypotheses. If all eliminated, form new hypotheses "
                "based on what you learned. Don't re-test eliminated paths."
            ),
            "text_to_process": build_error,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # ESM Evidence: Hypothesis tracking
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Expected: Hypothesis list with status
        hypothesis_markers = [
            k for k in {**artifacts, **scratchpad}.keys()
            if any(term in k.lower() for term in ["hypothesis", "tested", "eliminated", "debug"])
        ]

        # Verify no re-testing (routing history shouldn't show same diagnostic twice)
        routing_history = final_state.get("routing_history", [])
        _assert_no_unproductive_loops(routing_history)


@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="Requires hypothesis state injection. Stub for elimination tracking.")
def test_eliminated_hypothesis_not_retested(initialized_app):
    """
    Negative test: Verify eliminated hypotheses are not re-tested.

    Setup: Pre-populate state with eliminated hypotheses
    Expected: System should NOT test those hypotheses again
    """
    pytest.skip("Requires state injection capability - stub for architecture validation")


# ============================================================================
# TEST 5: Constraint Satisfaction with Backtracking
# ============================================================================

@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="ESM primitives not yet wired. Tests document expected behavior.")
def test_constraint_satisfaction_backtracking(initialized_app):
    """
    ESM Scenario: Meeting scheduling with constraint backtracking.

    Prompt: "Schedule these 5 meetings given these attendee constraints.
    If you hit an impossible constraint, backtrack to the last decision point
    and try an alternative, don't restart from scratch."

    Expected ESM Behavior:
    - State: SCHEDULING → (CONFLICT_AT_MEETING_N → BACKTRACK_TO_N-1) → COMPLETE
    - Decision tree tracked
    - Backtracking targeted to conflict point
    - Final schedule satisfies all constraints
    """
    app = initialized_app

    meeting_constraints = """
    Meetings to schedule:
    1. Team standup (15 min) - All team members
    2. Project review (1 hr) - Alice, Bob, Carol
    3. 1:1 Alice/Manager (30 min) - Alice, Manager
    4. Tech sync (45 min) - Bob, Carol, Dave
    5. Sprint planning (2 hr) - All team members

    Constraints:
    - Alice: Only available 9am-12pm
    - Bob: Not available Tuesday
    - Carol: Prefers afternoons
    - Dave: Only available Mon/Wed/Fri
    - Manager: Back-to-back meetings prohibited
    - All: No meetings during lunch (12-1pm)
    """

    with TestClient(app) as client:
        payload = {
            "input_prompt": (
                "Schedule these 5 meetings given the attendee constraints below. "
                "If you hit an impossible constraint, backtrack to the last decision "
                "point and try an alternative scheduling, don't restart from scratch."
            ),
            "text_to_process": meeting_constraints,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # ESM Evidence: Decision/backtracking tracking
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Expected: Schedule attempts and backtrack markers
        scheduling_markers = [
            k for k in {**artifacts, **scratchpad}.keys()
            if any(term in k.lower() for term in ["schedule", "backtrack", "conflict", "decision"])
        ]

        # Verify no unproductive loops
        routing_history = final_state.get("routing_history", [])
        _assert_no_unproductive_loops(routing_history)

        # Verify workflow completed
        assert final_state.get("error_report") is None


@pytest.mark.integration
@pytest.mark.esm
@pytest.mark.xfail(reason="Requires decision tree inspection. Stub for targeted backtrack.")
def test_backtrack_is_targeted_not_full_restart(initialized_app):
    """
    Granular test: Verify backtracking goes to specific decision point.

    This tests that the system doesn't naively restart when hitting a
    constraint violation, but instead backtracks to the relevant decision.
    """
    pytest.skip("Requires decision tree inspection - stub for architecture validation")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def _assert_no_unproductive_loops(routing_history: List[str], max_consecutive: int = 3):
    """
    Assert that no specialist appears consecutively more than max_consecutive times.

    Excludes orchestration nodes (router_specialist, check_task_completion).
    """
    orchestration_nodes = {"router_specialist", "check_task_completion"}

    # Filter to actual specialists
    specialists = [s for s in routing_history if s not in orchestration_nodes]

    if len(specialists) < max_consecutive:
        return

    for i in range(len(specialists) - max_consecutive + 1):
        window = specialists[i:i + max_consecutive]
        if len(set(window)) == 1:
            pytest.fail(
                f"Unproductive loop detected: {window[0]} repeated {max_consecutive} times. "
                f"Full history: {routing_history}"
            )


def _extract_esm_state(final_state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract ESM-related state from final workflow state.

    Looks for:
    - esm_state artifact
    - phase markers in scratchpad
    - decision tree artifacts
    - exhaustion tracking
    """
    artifacts = final_state.get("artifacts", {})
    scratchpad = final_state.get("scratchpad", {})

    esm_state = {}

    # Check for explicit ESM state
    if "esm_state" in artifacts:
        esm_state["explicit"] = artifacts["esm_state"]

    # Check for phase markers
    phase_keys = [k for k in scratchpad.keys() if "phase" in k.lower() or "state" in k.lower()]
    if phase_keys:
        esm_state["phases"] = {k: scratchpad[k] for k in phase_keys}

    # Check for exhaustion tracking
    exhaustion_keys = [k for k in artifacts.keys() if "exhausted" in k.lower() or "tried" in k.lower()]
    if exhaustion_keys:
        esm_state["exhaustion"] = {k: artifacts[k] for k in exhaustion_keys}

    # Check for decision tracking
    decision_keys = [k for k in artifacts.keys() if "decision" in k.lower() or "backtrack" in k.lower()]
    if decision_keys:
        esm_state["decisions"] = {k: artifacts[k] for k in decision_keys}

    return esm_state


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.

    Module-scoped to share expensive initialization across tests.
    """
    from app.src import api
    return api.app


