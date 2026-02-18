"""
Facilitator BENIGN interrupt tests: routing_context-driven early return.

ADR-077: Facilitator reads signals.routing_context == "benign_continuation" (set by
SignalProcessorSpecialist) instead of artifacts.max_iterations_exceeded.

Split from test_facilitator.py for maintainability.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.facilitator_specialist import FacilitatorSpecialist


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
# Issue #108/114 / ADR-077: BENIGN Interrupts via routing_context
# =============================================================================

def test_facilitator_passes_trace_on_benign_interrupt(facilitator):
    """
    ADR-077: BENIGN interrupt early-returns when routing_context is benign_continuation.

    Signal processor already classified this as BENIGN. Facilitator early-returns
    without re-executing triage actions.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Continue interrupted task",
        },
        "artifacts": {},
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["animals/", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    assert "gathered_context" not in result["artifacts"]


def test_facilitator_no_wip_summary_without_benign_context(facilitator):
    """
    Issue #108: No work-in-progress summary for normal flow (no BENIGN routing_context).
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Normal execution",
        },
        "artifacts": {},
        "signals": {},
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
    ADR-077: BENIGN continuation when routing_context is benign_continuation
    and EI said INCOMPLETE.

    This is BENIGN continuation (model was working, ran out of runway), not correction.
    Facilitator early-returns without re-executing triage actions.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Retry after Exit Interview",
        },
        "artifacts": {
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not fully categorized"
            },
        },
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    assert "gathered_context" not in result["artifacts"]


def test_facilitator_benign_early_returns_minimal_state(facilitator):
    """
    BENIGN always early-returns with minimal state.

    Signal processor set routing_context=benign_continuation. Facilitator
    early-returns. Context was already gathered in the first Facilitator pass
    and persists in artifacts via ior merge.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Continue interrupted task",
        },
        "artifacts": {},
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # BENIGN early return — no filesystem calls
        mock_list.assert_not_called()

    assert "gathered_context" not in result["artifacts"]


def test_facilitator_benign_does_not_accumulate_context(facilitator):
    """
    ADR-077: BENIGN early return avoids context pollution.

    When routing_context is benign_continuation, Facilitator early-returns without
    re-gathering context. gathered_context from the first pass persists via ior merge.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "Task interrupted mid-work",
        },
        "artifacts": {
            "gathered_context": "### Directory: /workspace/test\n- [FILE] 1.txt",
        },
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: No filesystem calls (early return)
        mock_list.assert_not_called()

    # Minimal return: no new gathered_context (prior pass persists via ior)
    assert "gathered_context" not in result["artifacts"]


def test_facilitator_benign_early_returns_empty_routing_history(facilitator):
    """
    BENIGN early-returns even with empty routing history.

    Signal processor set routing_context=benign_continuation. Facilitator
    early-returns. Context was gathered on the first Facilitator pass and persists
    via ior merge — no need to re-gather.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "First run, no prior trace",
        },
        "artifacts": {},
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": []
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # BENIGN: no filesystem calls (early return)
        mock_list.assert_not_called()

    assert "gathered_context" not in result["artifacts"]


def test_facilitator_no_early_return_when_exit_interview_result_present(facilitator):
    """
    Issue #114: When exit_interview_result is present (without benign routing_context),
    this is EI retry, NOT BENIGN. Facilitator re-gathers context normally.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "Exit Interview retry",
        },
        "artifacts": {
            # Exit Interview result IS present - this is EI retry, not BENIGN
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not all categorized",
                "missing_elements": "3.txt not moved",
                "recommended_specialists": ["project_director"]
            }
        },
        "signals": {},  # No benign routing_context
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
    ADR-077: BENIGN+INCOMPLETE = continuation, not correction.

    When routing_context=benign_continuation AND EI says INCOMPLETE, Facilitator
    early-returns but surfaces specialist_activity and EI feedback into
    gathered_context so Router has context for correct routing and PD knows
    what it already did.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "Task interrupted mid-work",
            "specialist_activity": [
                "Moved /workspace/inbox/a.txt → /workspace/docs/a.txt",
                "Created directory /workspace/images",
            ],
        },
        "artifacts": {
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Only 1 of 6 files categorized",
                "missing_elements": "5 files still need categorization",
                "recommended_specialists": ["project_director"],
            }
        },
        "signals": {"routing_context": "benign_continuation"},
        "routing_history": ["project_director", "exit_interview_specialist"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # Early return — no re-gathering of triage actions
        mock_list.assert_not_called()

    # Surfaces continuation context for Router and PD
    assert "gathered_context" in result["artifacts"]
    gathered = result["artifacts"]["gathered_context"]

    # EI feedback surfaced
    assert "5 files still need categorization" in gathered

    # specialist_activity surfaced
    assert "Moved /workspace/inbox/a.txt" in gathered
    assert "Created directory /workspace/images" in gathered
