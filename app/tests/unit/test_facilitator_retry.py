"""
Facilitator retry context tests: context rebuild, EI feedback, scratchpad.

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
# Issue #96: Context Accumulation on Exit Interview Retry
# =============================================================================

def test_facilitator_rebuilds_context_fresh_on_retry(facilitator):
    """
    #170: Facilitator rebuilds gathered_context fresh each invocation.

    The old behavior (Issue #96) accumulated context across retries, causing
    tripling. Now each invocation builds from the current plan actions only.
    Stale prior context from artifacts is NOT carried forward.
    """
    plan = ContextPlan(
        reasoning="Re-check directory state on retry",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    # Simulate RETRY state: gathered_context exists from first pass (should be ignored)
    existing_context = """### Directory: /workspace/test
- [FILE] /workspace/test/1.txt
- [FILE] /workspace/test/2.txt"""

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
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
    plan = ContextPlan(
        reasoning="First pass context gathering",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="/workspace/test",
                description="List directory"
            )
        ]
    )

    # Fresh state: NO pre-existing gathered_context
    state = {
        "artifacts": {
            "context_plan": plan.model_dump()
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


def test_facilitator_does_not_relay_resume_trace(facilitator):
    """
    #170: Facilitator does NOT relay resume_trace in non-BENIGN path.

    PD writes resume_trace directly to artifacts (ior merge). Facilitator
    only reads it for _extract_trace_knowledge(). On first pass (no EI result),
    Facilitator builds gathered_context without trace knowledge.
    """
    plan = ContextPlan(
        reasoning="Continue task after partial completion",
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
            "resume_trace": [
                {"tool": "create_directory", "args": {"path": "/workspace/animals"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
            ]
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["3.txt", "[DIR] animals"]
        result = facilitator.execute(state)

    # #170: Facilitator does NOT relay resume_trace (PD wrote it directly)
    assert "resume_trace" not in result["artifacts"]
    # gathered_context should have directory listing but NOT trace knowledge
    # (no EI result = first pass, trace knowledge only on retry)
    gathered = result["artifacts"]["gathered_context"]
    assert "### Directory: /workspace" in gathered


def test_facilitator_surfaces_curated_exit_interview_feedback(facilitator):
    """
    Issue #167 (revises #121): Curated EI feedback IS surfaced in gathered_context.

    #121 removed raw EI dumps that polluted context. #167 re-enables a curated
    version: only missing_elements + reasoning, no routing data.
    """
    plan = ContextPlan(
        reasoning="Continue task after Exit Interview flagged incomplete",
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
    plan = ContextPlan(
        reasoning="Retry",
        actions=[]
    )

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Files not moved",
                "missing_elements": "Move remaining files",
                "recommended_specialists": ["project_director", "web_specialist"]
            }
        }
    }

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
    Issue #167: Triage reasoning should appear in gathered_context so PD
    understands the strategic intent behind the task.
    """
    plan = ContextPlan(
        reasoning="User wants files sorted by content into category subfolders",
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
    plan = ContextPlan(
        reasoning="Sort files into categories",
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
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "Only 2 of 6 files moved",
                "missing_elements": "4 files still need moving",
                "recommended_specialists": ["project_director"]
            },
        },
        "scratchpad": {
            "specialist_activity": [
                "Created directory /workspace/animals",
                "Moved /workspace/1.txt \u2192 /workspace/animals/1.txt",
                "Moved /workspace/4.txt \u2192 /workspace/animals/4.txt",
            ]
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
