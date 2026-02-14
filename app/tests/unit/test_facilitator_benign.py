"""
Facilitator BENIGN interrupt tests: max_iterations handling, early return.

Split from test_facilitator.py for maintainability.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.facilitator_specialist import FacilitatorSpecialist
from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType


@pytest.fixture
def facilitator():
    config = {}
    specialist = FacilitatorSpecialist("facilitator_specialist", config)
    specialist.mcp_client = MagicMock()

    # Mock external MCP client for filesystem operations (ADR-CORE-035)
    specialist.external_mcp_client = MagicMock()
    specialist.external_mcp_client.is_connected.return_value = True

    return specialist


# =============================================================================
# Issue #108/114 / ADR-073 Phase 4: BENIGN Interrupts
# =============================================================================

def test_facilitator_passes_trace_on_benign_interrupt(facilitator):
    """
    ADR-073 Phase 4: BENIGN interrupt early-returns, clearing the flag.

    When max_iterations_exceeded is set (BENIGN interrupt), Facilitator should
    early return clearing the flag.
    """
    plan = ContextPlan(
        reasoning="Continue interrupted task",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace",
                description="List workspace"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
        },
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["animals/", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    # Only clears the flag
    assert "gathered_context" not in result["artifacts"]
    assert result["artifacts"]["max_iterations_exceeded"] is False


def test_facilitator_no_wip_summary_without_max_iterations(facilitator):
    """
    Issue #108: No work-in-progress summary for normal flow (no BENIGN interrupt).
    """
    plan = ContextPlan(
        reasoning="Normal execution",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace",
                description="List workspace"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            # NO max_iterations_exceeded - normal flow
        },
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Should NOT have work-in-progress summary
    assert "## Work In Progress" not in gathered


def test_facilitator_benign_continuation_with_ei_incomplete(facilitator):
    """
    ADR-073 Phase 4: BENIGN continuation when EI says INCOMPLETE but max_iterations caused it.

    When max_iterations_exceeded=True AND exit_interview_result.is_complete=False,
    this is BENIGN continuation (model was working, ran out of runway), not correction.
    Facilitator early-returns clearing the flag.
    """
    plan = ContextPlan(
        reasoning="Retry after Exit Interview",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace",
                description="List workspace"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not fully categorized"
            },
        },
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    # Only clears the flag
    assert "gathered_context" not in result["artifacts"]
    assert result["artifacts"]["max_iterations_exceeded"] is False


def test_facilitator_benign_early_returns_minimal_state(facilitator):
    """
    BENIGN always early-returns with minimal state.

    max_iterations_exceeded means the model was mid-work. Facilitator clears the
    flag. Context was already gathered in the first Facilitator pass and persists
    in artifacts via ior merge.
    """
    plan = ContextPlan(
        reasoning="Continue interrupted task",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace",
                description="List workspace"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
        },
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # BENIGN early return — no filesystem calls
        mock_list.assert_not_called()

    # Only clears the flag
    assert result["artifacts"]["max_iterations_exceeded"] is False
    assert "gathered_context" not in result["artifacts"]


def test_facilitator_benign_does_not_accumulate_context(facilitator):
    """
    ADR-073 Phase 4: BENIGN early return avoids context pollution.

    When max_iterations fires, Facilitator early-returns without re-gathering
    context. gathered_context from the first pass persists via ior merge.
    """
    plan = ContextPlan(
        reasoning="Task interrupted mid-work",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "gathered_context": "### Directory: /workspace/test\n- [FILE] 1.txt",
            "max_iterations_exceeded": True,
        },
        "scratchpad": {},
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: No filesystem calls (early return)
        mock_list.assert_not_called()

    # Minimal return: only clear the flag
    assert "gathered_context" not in result["artifacts"]
    assert result["artifacts"]["max_iterations_exceeded"] is False
    assert result["scratchpad"] == {"facilitator_complete": True}


def test_facilitator_benign_early_returns_empty_routing_history(facilitator):
    """
    BENIGN early-returns even with empty routing history.

    max_iterations_exceeded means the model was working. Facilitator clears
    the flag. Context was gathered on the first Facilitator pass and persists
    via ior merge — no need to re-gather.
    """
    plan = ContextPlan(
        reasoning="First run, no prior trace",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
        },
        "scratchpad": {},
        "routing_history": []
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # BENIGN: no filesystem calls (early return)
        mock_list.assert_not_called()

    assert result["artifacts"]["max_iterations_exceeded"] is False
    assert "gathered_context" not in result["artifacts"]


def test_facilitator_no_early_return_when_exit_interview_result_present(facilitator):
    """
    Issue #114: When exit_interview_result is present (without max_iterations),
    this is EI retry, NOT BENIGN. Facilitator re-gathers context normally.
    """
    plan = ContextPlan(
        reasoning="Exit Interview retry",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            # Exit Interview result IS present - this is EI retry, not BENIGN
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not all categorized",
                "missing_elements": "3.txt not moved",
                "recommended_specialists": ["project_director"]
            }
        },
        "scratchpad": {},
        "routing_history": ["exit_interview_specialist"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # _list_directory SHOULD be called (not early return)
        mock_list.assert_called_once()

    # Result should have gathered_context
    assert "gathered_context" in result["artifacts"]
    # Issue #121: EI feedback should NOT be present (Router uses recommended_specialists)
    assert "### Next Steps (from Exit Interview)" not in result["artifacts"]["gathered_context"]
    # But directory listing should be present
    assert "1.txt" in result["artifacts"]["gathered_context"]


def test_facilitator_benign_continuation_after_ei_incomplete(facilitator):
    """
    ADR-073 Phase 4: BENIGN+INCOMPLETE = continuation, not correction.

    When max_iterations_exceeded=True AND EI says INCOMPLETE, Facilitator
    early-returns clearing the flag. This is continuation (model was working),
    not correction (model was wrong).
    """
    plan = ContextPlan(
        reasoning="Task interrupted mid-work",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Only 1 of 6 files categorized",
                "missing_elements": "5 files still need categorization",
                "recommended_specialists": ["project_director"],
            }
        },
        "scratchpad": {},
        "routing_history": ["project_director", "exit_interview_specialist"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # Early return — no re-gathering
        mock_list.assert_not_called()

    assert "gathered_context" not in result["artifacts"]
    assert result["artifacts"]["max_iterations_exceeded"] is False
    assert result["scratchpad"] == {"facilitator_complete": True}
