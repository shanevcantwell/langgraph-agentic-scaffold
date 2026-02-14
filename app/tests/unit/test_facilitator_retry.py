"""
Facilitator retry context tests: context rebuild, EI feedback, scratchpad.

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
# Issue #96: Context Accumulation on Exit Interview Retry
# =============================================================================

def test_facilitator_rebuilds_context_fresh_on_retry(facilitator):
    """
    #170: Facilitator rebuilds gathered_context fresh each invocation.

    The old behavior (Issue #96) accumulated context across retries, causing
    tripling. Now each invocation builds from the current plan actions only.
    Stale prior context from artifacts is NOT carried forward.
    """
    # Simulate RETRY state: gathered_context exists from first pass (should be ignored)
    existing_context = """### Directory: /workspace/test
- [FILE] /workspace/test/1.txt
- [FILE] /workspace/test/2.txt"""

    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "Re-check directory state on retry",
        },
        "artifacts": {
            "gathered_context": existing_context  # Should NOT be preserved
        }
    }

    # Second pass: directory listing returns updated state
    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "[DIR] animals"]  # 1.txt already moved
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # #170: Fresh rebuild — shows CURRENT directory state, not accumulated old + new
    assert "2.txt" in gathered  # Current listing
    assert "animals" in gathered  # Current listing
    # Old content should NOT be preserved (no accumulation)
    assert "- [FILE] /workspace/test/1.txt" not in gathered

    # New context should be appended
    assert "- /workspace/test/2.txt" in gathered  # From new listing
    assert "animals" in gathered  # From new listing


def test_facilitator_fresh_context_when_no_existing(facilitator):
    """
    Issue #96: First pass (no existing gathered_context) should work normally.

    This is the baseline case - just like before the fix.
    """
    # Fresh state: NO pre-existing gathered_context
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace/test", "description": "List directory", "strategy": None}
            ],
            "triage_reasoning": "First pass context gathering",
        },
        "artifacts": {
            # No gathered_context key
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Should have directory listing but NO separator (no accumulation needed)
    assert "### Directory: /workspace/test" in gathered
    assert "- /workspace/test/1.txt" in gathered

    # Should NOT have separator (indicates fresh, not accumulated)
    # Count how many times '---' appears - should be 0 for fresh context
    separator_count = gathered.count("\n---\n")
    assert separator_count == 0, f"Fresh context should not have separators, found {separator_count}"


def test_facilitator_first_pass_builds_gathered_context(facilitator):
    """
    #170: First pass (no EI result) builds gathered_context from plan actions.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Continue task after partial completion",
        },
        "artifacts": {}
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["3.txt", "[DIR] animals"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]
    assert "### Directory: /workspace" in gathered


def test_facilitator_surfaces_curated_exit_interview_feedback(facilitator):
    """
    Issue #167 (revises #121): Curated EI feedback IS surfaced in gathered_context.

    #121 removed raw EI dumps that polluted context. #167 re-enables a curated
    version: only missing_elements + reasoning, no routing data.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Continue task after Exit Interview flagged incomplete",
        },
        "artifacts": {
            # Exit Interview marked task incomplete
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Only 3 of 6 files were categorized",
                "missing_elements": "Files 4.txt, 5.txt, 6.txt need categorization",
                "recommended_specialists": ["project_director"]
            }
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["animals/", "plants/", "4.txt", "5.txt", "6.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # #167: Curated feedback IS present
    assert "Retry Context" in gathered
    assert "Files 4.txt, 5.txt, 6.txt" in gathered
    assert "Only 3 of 6" in gathered
    # Routing data should NOT appear in gathered_context
    assert "project_director" not in gathered
    # Directory listing should still be present
    assert "Directory:" in gathered
    assert "4.txt" in gathered


def test_facilitator_curated_feedback_excludes_routing_data(facilitator):
    """
    Issue #167: Curated feedback should contain only missing_elements and reasoning,
    NOT recommended_specialists (that's for Router, not PD).
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Retry",
        },
        "artifacts": {
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not moved",
                "missing_elements": "Move remaining files",
                "recommended_specialists": ["project_director", "web_specialist"]
            }
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    assert "Move remaining files" in gathered
    assert "Files not moved" in gathered
    # Routing recommendations should not leak into gathered_context
    assert "web_specialist" not in gathered


def test_facilitator_skips_exit_interview_feedback_when_complete(facilitator):
    """
    Issue #100: Facilitator should NOT add feedback when task was marked complete.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Normal execution",
        },
        "artifacts": {
            # Exit Interview marked task COMPLETE
            "exit_interview_result": {
                "is_complete": True,
                "reasoning": "All files categorized successfully"
            }
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["animals/", "plants/"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Should NOT have Exit Interview feedback since task was complete
    assert "Retry Context" not in gathered


def test_context_plan_reasoning_in_gathered_context(facilitator):
    """
    Issue #167: Task strategy should appear in gathered_context so PD
    understands the strategic intent behind the task.

    Task Strategy now comes from artifacts["task_plan"]["plan_summary"]
    (set by SA) instead of triage reasoning.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Triage reasoning here (not used for Task Strategy)",
        },
        "artifacts": {
            "task_plan": {
                "plan_summary": "User wants files sorted by content into category subfolders",
                "execution_steps": [],
                "required_components": []
            },
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    assert "### Task Strategy" in gathered
    assert "sorted by content into category subfolders" in gathered


# =============================================================================
# ADR-073 Phase 3: Scratchpad-based Prior Work
# =============================================================================

def test_facilitator_surfaces_specialist_activity_on_retry(facilitator):
    """
    ADR-073 Phase 3: On EI retry, Facilitator reads specialist_activity from
    scratchpad (written by PD) and includes it in gathered_context.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Sort files into categories",
            "specialist_activity": [
                "Created directory /workspace/animals",
                "Moved /workspace/1.txt \u2192 /workspace/animals/1.txt",
                "Moved /workspace/4.txt \u2192 /workspace/animals/4.txt",
            ]
        },
        "artifacts": {
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Only 2 of 6 files moved",
                "missing_elements": "4 files still need moving",
                "recommended_specialists": ["project_director"]
            },
            "task_plan": {
                "plan_summary": "Sort files into categories",
                "execution_steps": [],
                "required_components": []
            },
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "3.txt", "5.txt", "6.txt", "[DIR] animals"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Task strategy
    assert "### Task Strategy" in gathered
    # EI feedback
    assert "4 files still need moving" in gathered
    # Prior work from scratchpad
    assert "### Prior Work Completed" in gathered
    assert "Created directory /workspace/animals" in gathered
    assert "Moved /workspace/1.txt" in gathered
    assert "Moved /workspace/4.txt" in gathered
