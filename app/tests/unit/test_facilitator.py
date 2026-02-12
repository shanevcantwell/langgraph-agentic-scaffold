import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.facilitator_specialist import FacilitatorSpecialist
from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType


def _make_mcp_result(text: str):
    """Create mock MCP result with expected structure for extract_text_from_mcp_result."""
    mock_content = MagicMock()
    mock_content.text = text
    mock_result = MagicMock()
    mock_result.content = [mock_content]
    return mock_result

@pytest.fixture
def facilitator():
    config = {}
    specialist = FacilitatorSpecialist("facilitator_specialist", config)
    specialist.mcp_client = MagicMock()

    # Mock external MCP client for filesystem operations (ADR-CORE-035)
    specialist.external_mcp_client = MagicMock()
    specialist.external_mcp_client.is_connected.return_value = True

    return specialist

def test_facilitator_executes_research_action(facilitator):
    # Arrange
    plan = ContextPlan(
        reasoning="Need info",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="LangGraph", description="Search")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }
    
    facilitator.mcp_client.call.return_value = [{"title": "Result", "url": "url", "snippet": "snippet"}]
    
    # Act
    result = facilitator.execute(state)
    
    # Assert
    assert "artifacts" in result
    assert "gathered_context" in result["artifacts"]
    assert "### Research: LangGraph" in result["artifacts"]["gathered_context"]
    
    facilitator.mcp_client.call.assert_called_with(
        service_name="web_specialist",
        function_name="search",
        query="LangGraph"
    )

def test_facilitator_executes_read_file_action(facilitator):
    # Arrange
    plan = ContextPlan(
        reasoning="Need file",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="/path/to/file", description="Read")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # Act - Mock external MCP call (ADR-CORE-035: file ops via filesystem container)
    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("File content")
        result = facilitator.execute(state)

    # Assert
    assert "### File: /path/to/file" in result["artifacts"]["gathered_context"]
    assert "File content" in result["artifacts"]["gathered_context"]

def test_facilitator_handles_missing_plan(facilitator):
    state = {"artifacts": {}}
    result = facilitator.execute(state)
    assert "error" in result

def test_facilitator_handles_mcp_error(facilitator):
    plan = ContextPlan(
        reasoning="Need info",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="LangGraph", description="Search")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    facilitator.mcp_client.call.side_effect = Exception("MCP Error")

    result = facilitator.execute(state)

    assert "### Error: LangGraph" in result["artifacts"]["gathered_context"]

def test_facilitator_reads_artifact_instead_of_file_for_uploaded_image(facilitator):
    """Test that Facilitator retrieves in-memory artifacts instead of trying to read from filesystem."""
    # Arrange
    plan = ContextPlan(
        reasoning="Need to analyze uploaded image",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="/artifacts/image.png", description="Read image")
        ]
    )
    image_data = "data:image/png;base64,iVBORw0KGgoAAAANS..."
    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "image.png": image_data  # Image already in artifacts
        }
    }

    # Act
    result = facilitator.execute(state)

    # Assert
    assert "artifacts" in result
    assert "gathered_context" in result["artifacts"]
    assert "### Image: image.png" in result["artifacts"]["gathered_context"]
    assert "[Image data available in artifacts" in result["artifacts"]["gathered_context"]
    # MCP should NOT have been called for file read
    facilitator.mcp_client.call.assert_not_called()

def test_facilitator_reads_artifact_for_uploaded_image_png_key(facilitator):
    """Test artifact retrieval with 'uploaded_image.png' key."""
    plan = ContextPlan(
        reasoning="Need to analyze uploaded image",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="uploaded_image.png", description="Read image")
        ]
    )
    image_data = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA..."
    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "uploaded_image.png": image_data
        }
    }

    # Act
    result = facilitator.execute(state)

    # Assert
    assert "### Image: uploaded_image.png" in result["artifacts"]["gathered_context"]
    facilitator.mcp_client.call.assert_not_called()

def test_facilitator_reads_file_via_external_mcp_when_artifact_not_in_state(facilitator):
    """Test that Facilitator reads files via external filesystem MCP when not in artifacts."""
    plan = ContextPlan(
        reasoning="Need actual file from workspace",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="config.yaml", description="Read config")
        ]
    )
    state = {
        "artifacts": {
            "context_plan": plan.model_dump()
            # No "config.yaml" in artifacts
        }
    }

    # Act - Mock external MCP call (ADR-CORE-035: file ops via filesystem container)
    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("yaml content")
        result = facilitator.execute(state)

    # Assert
    assert "### File: config.yaml" in result["artifacts"]["gathered_context"]
    assert "yaml content" in result["artifacts"]["gathered_context"]
    # External MCP should have been called
    mock_sync.assert_called_once()


def test_facilitator_directory_listing_includes_full_paths(facilitator):
    """
    Regression test for Bug #49: Directory listing must include full paths.

    When Facilitator lists a directory, each item must include the parent
    directory path. Otherwise, downstream specialists (like BatchProcessor)
    generate file operations with incomplete paths (e.g., "b.txt" instead
    of "subdir/b.txt").
    """
    plan = ContextPlan(
        reasoning="Need to see directory contents",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="sort_by_contents",
                description="List files to sort"
            )
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # Mock the filesystem MCP to return directory contents
    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["a.txt", "b.txt", "c.txt"]
        result = facilitator.execute(state)

    # Assert full paths are in the gathered context
    gathered = result["artifacts"]["gathered_context"]
    assert "### Directory: sort_by_contents" in gathered
    assert "- sort_by_contents/a.txt" in gathered
    assert "- sort_by_contents/b.txt" in gathered
    assert "- sort_by_contents/c.txt" in gathered

    # Should NOT have bare filenames without path
    lines = gathered.split('\n')
    file_lines = [l for l in lines if l.startswith('- ') and not l.startswith('- [DIR]')]
    for line in file_lines:
        # Each file line should contain the parent directory
        assert "sort_by_contents/" in line, f"Missing full path in: {line}"


def test_facilitator_directory_listing_handles_subdirs(facilitator):
    """
    Test that [DIR] markers are properly formatted with full paths.
    """
    plan = ContextPlan(
        reasoning="Need to see directory contents",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target="workspace",
                description="List workspace"
            )
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt", "[DIR] subdir", "[DIR] another"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]
    assert "- workspace/file.txt" in gathered
    assert "- [DIR] workspace/subdir" in gathered
    assert "- [DIR] workspace/another" in gathered


# =============================================================================
# Tests derived from FACILITATOR.md briefing
# =============================================================================

def test_facilitator_executes_summarize_action(facilitator):
    """
    Per FACILITATOR.md: SUMMARIZE action calls summarizer_specialist.summarize.
    """
    plan = ContextPlan(
        reasoning="Need summary",
        actions=[
            ContextAction(
                type=ContextActionType.SUMMARIZE,
                target="This is a very long document with many details...",
                description="Summarize the content"
            )
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    facilitator.mcp_client.call.return_value = "A concise summary of the document."

    result = facilitator.execute(state)

    # Verify MCP call
    facilitator.mcp_client.call.assert_called_with(
        service_name="summarizer_specialist",
        function_name="summarize",
        text="This is a very long document with many details..."
    )

    # Verify output format
    assert "### Summary:" in result["artifacts"]["gathered_context"]
    assert "A concise summary of the document." in result["artifacts"]["gathered_context"]


def test_facilitator_summarize_with_file_path_reads_file_first(facilitator):
    """
    Per FACILITATOR.md: If SUMMARIZE target looks like a file path (starts with / or ./),
    Facilitator reads the file first, then summarizes the content.
    """
    plan = ContextPlan(
        reasoning="Summarize a file",
        actions=[
            ContextAction(
                type=ContextActionType.SUMMARIZE,
                target="/workspace/long_document.md",
                description="Summarize the document"
            )
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # Mock file read to return document content
    with patch.object(facilitator, '_read_file_via_filesystem_mcp') as mock_read:
        mock_read.return_value = "Full document content here..."
        facilitator.mcp_client.call.return_value = "Summary of document"

        result = facilitator.execute(state)

    # File should have been read
    mock_read.assert_called_once_with("/workspace/long_document.md")

    # Summarizer should have been called with file CONTENT, not path
    facilitator.mcp_client.call.assert_called_with(
        service_name="summarizer_specialist",
        function_name="summarize",
        text="Full document content here..."
    )


def test_facilitator_handles_ask_user_action_via_interrupt(facilitator):
    """
    ADR-CORE-059: Facilitator handles ASK_USER inline via LangGraph interrupt().
    DialogueSpecialist is deprecated - ASK_USER is just another context tool.
    """
    from unittest.mock import patch

    plan = ContextPlan(
        reasoning="Need user clarification",
        actions=[
            ContextAction(
                type=ContextActionType.ASK_USER,
                target="What file format do you prefer?",
                description="Clarify user preference"
            )
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # Mock interrupt() to simulate user providing clarification
    # interrupt is imported locally in facilitator_specialist.py, so patch at source
    with patch("langgraph.types.interrupt") as mock_interrupt:
        mock_interrupt.return_value = "I prefer JSON format"

        result = facilitator.execute(state)

        # Verify interrupt was called with the question
        mock_interrupt.assert_called_once()
        call_payload = mock_interrupt.call_args[0][0]
        assert call_payload["action_type"] == "ask_user"
        # question_text uses action.description (or action.target if description is empty)
        assert "clarify user preference" in call_payload["question"].lower()

    # No MCP calls should have been made (ASK_USER uses interrupt, not MCP)
    facilitator.mcp_client.call.assert_not_called()

    # User's clarification should be in gathered_context
    assert "I prefer JSON format" in result["artifacts"]["gathered_context"]
    assert "User Clarification" in result["artifacts"]["gathered_context"]

    # Completion flag should be set
    assert result["scratchpad"]["facilitator_complete"] is True


def test_facilitator_executes_multiple_actions(facilitator):
    """
    Per FACILITATOR.md: Facilitator processes all actions in the plan sequentially,
    joining results with double newlines.
    """
    plan = ContextPlan(
        reasoning="Need multiple context sources",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="topic1", description="Search topic1"),
            ContextAction(type=ContextActionType.RESEARCH, target="topic2", description="Search topic2"),
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    facilitator.mcp_client.call.side_effect = [
        [{"title": "Result1", "url": "url1", "snippet": "snippet1"}],
        [{"title": "Result2", "url": "url2", "snippet": "snippet2"}],
    ]

    result = facilitator.execute(state)

    # Both actions should be executed
    assert facilitator.mcp_client.call.call_count == 2

    # Both results should appear in gathered_context, separated by double newline
    gathered = result["artifacts"]["gathered_context"]
    assert "### Research: topic1" in gathered
    assert "### Research: topic2" in gathered
    assert "\n\n" in gathered  # Sections joined with double newline


def test_facilitator_sets_completion_flag(facilitator):
    """
    Per FACILITATOR.md: Facilitator sets scratchpad["facilitator_complete"] = True
    after processing all actions.
    """
    plan = ContextPlan(
        reasoning="Simple action",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="test", description="test")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    facilitator.mcp_client.call.return_value = []

    result = facilitator.execute(state)

    assert "scratchpad" in result
    assert result["scratchpad"]["facilitator_complete"] is True


def test_facilitator_filesystem_unavailable_graceful_degradation(facilitator):
    """
    Per FACILITATOR.md: If filesystem MCP is unavailable, Facilitator includes
    "[Filesystem service unavailable]" message and continues.
    """
    plan = ContextPlan(
        reasoning="Need file",
        actions=[
            ContextAction(type=ContextActionType.READ_FILE, target="/path/to/file", description="Read file")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # Mock filesystem as unavailable
    facilitator.external_mcp_client.is_connected.return_value = False

    result = facilitator.execute(state)

    # Should show unavailable message, not error
    gathered = result["artifacts"]["gathered_context"]
    assert "### File: /path/to/file" in gathered
    assert "[Filesystem service unavailable]" in gathered

    # Completion flag still set
    assert result["scratchpad"]["facilitator_complete"] is True


def test_facilitator_directory_listing_filesystem_unavailable(facilitator):
    """
    Per FACILITATOR.md: LIST_DIRECTORY also gracefully handles filesystem unavailability.
    """
    plan = ContextPlan(
        reasoning="List directory",
        actions=[
            ContextAction(type=ContextActionType.LIST_DIRECTORY, target="/workspace", description="List")
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    facilitator.external_mcp_client.is_connected.return_value = False

    result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]
    assert "### Directory: /workspace" in gathered
    assert "[Filesystem service unavailable]" in gathered


def test_facilitator_handles_invalid_context_plan(facilitator):
    """
    Per FACILITATOR.md: Invalid ContextPlan data returns an error.
    """
    state = {
        "artifacts": {
            "context_plan": {"invalid": "structure"}  # Missing required fields
        }
    }

    result = facilitator.execute(state)

    assert "error" in result
    assert "Invalid context plan" in result["error"]


def test_facilitator_continues_after_action_error(facilitator):
    """
    Per FACILITATOR.md: Individual action failures don't halt the entire plan.
    Error is logged and next action continues.
    """
    plan = ContextPlan(
        reasoning="Multiple actions with one failing",
        actions=[
            ContextAction(type=ContextActionType.RESEARCH, target="failing_query", description="Will fail"),
            ContextAction(type=ContextActionType.RESEARCH, target="success_query", description="Will succeed"),
        ]
    )
    state = {
        "artifacts": {"context_plan": plan.model_dump()}
    }

    # First call fails, second succeeds
    facilitator.mcp_client.call.side_effect = [
        Exception("Network error"),
        [{"title": "Success", "url": "url", "snippet": "snippet"}],
    ]

    result = facilitator.execute(state)

    # Both actions attempted
    assert facilitator.mcp_client.call.call_count == 2

    # Error for first, success for second
    gathered = result["artifacts"]["gathered_context"]
    assert "### Error: failing_query" in gathered
    assert "Network error" in gathered
    assert "### Research: success_query" in gathered
    assert "Success" in gathered

    # Completion flag still set
    assert result["scratchpad"]["facilitator_complete"] is True


# =============================================================================
# Issue #96: Context Accumulation on Exit Interview Retry
# =============================================================================

def test_facilitator_accumulates_existing_context_on_retry(facilitator):
    """
    Issue #96: Facilitator should ACCUMULATE context, not OVERWRITE.

    When Exit Interview routes back through Facilitator for retry, the existing
    gathered_context must be preserved and new context appended. Without this,
    specialists see stale/incomplete context and create hedged duplicates
    (e.g., "Plant_new" instead of continuing with "Plant").

    The fix is += not = for gathered_context.
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

    # Simulate RETRY state: gathered_context already exists from first pass
    existing_context = """### Directory: /workspace/test
- [FILE] /workspace/test/1.txt
- [FILE] /workspace/test/2.txt

### Previous Work (do not repeat these operations)
**research_trace_0:**
- create_directory ✓: {'path': '/workspace/test/animals'}
- move_file ✓: {'source': '/workspace/test/1.txt', 'destination':"""

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "gathered_context": existing_context  # PRE-EXISTING from first pass
        }
    }

    # Second pass: directory listing returns updated state
    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "[DIR] animals"]  # 1.txt already moved
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # CRITICAL: Existing context MUST be preserved (not overwritten)
    assert "### Directory: /workspace/test" in gathered  # From existing
    assert "- [FILE] /workspace/test/1.txt" in gathered  # From existing (original state)
    assert "### Previous Work" in gathered  # From existing

    # Separator should be present (indicates accumulation, not overwrite)
    assert "---" in gathered

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


def test_facilitator_assembles_resume_trace_for_prior_work(facilitator):
    """
    ADR-CORE-059: Facilitator assembles resume_trace from prior research traces.

    Instead of summarizing prior work in gathered_context (prompt engineering),
    we give the specialist its actual trace to resume from (context engineering).
    The model sees its own tool conversation and continues naturally.
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
            # Simulate previous work recorded in research_trace
            "resume_trace": [
                {"tool": "create_directory", "args": {"path": "/workspace/animals"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/2.txt", "destination": "/workspace/animals/2.txt"}, "success": False, "error": "Hit iteration limit"},
            ]
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["3.txt", "[DIR] animals"]
        result = facilitator.execute(state)

    # ADR-CORE-059: Prior work is now provided as resume_trace, NOT in gathered_context
    assert "resume_trace" in result["artifacts"]
    resume_trace = result["artifacts"]["resume_trace"]

    # All 3 trace entries should be assembled
    assert len(resume_trace) == 3

    # Verify trace entries are passed through correctly
    assert resume_trace[0]["tool"] == "create_directory"
    assert resume_trace[1]["tool"] == "move_file"
    assert resume_trace[2]["tool"] == "move_file"
    assert resume_trace[2]["success"] is False  # Failed operation preserved

    # gathered_context should NOT contain the old summary format
    gathered = result["artifacts"]["gathered_context"]
    assert "### Previous Work" not in gathered
    assert "do not repeat these operations" not in gathered


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
# Issue #108/114: BENIGN Interrupts - Trace Passthrough
# =============================================================================
# Issue #108 originally added WIP summaries. Issue #114 supersedes this with
# trace passthrough - model sees its actual conversation history instead of
# a summary. WIP summaries are no longer generated when early return triggers.
# =============================================================================

def test_facilitator_passes_trace_on_benign_interrupt(facilitator):
    """
    Issue #114 supersedes Issue #108: BENIGN interrupt passes trace, not WIP summary.

    When max_iterations_exceeded is set (BENIGN interrupt), Facilitator should
    early return with the resume_trace so the model can continue its conversation.
    The model doesn't need a summary - it sees its actual tool call history.
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

    original_trace = [
        {"tool": "list_directory", "args": {"path": "/workspace"}, "success": True},
        {"tool": "read_file", "args": {"path": "/workspace/1.txt"}, "success": True},
        {"tool": "read_file", "args": {"path": "/workspace/2.txt"}, "success": True},
        {"tool": "create_directory", "args": {"path": "/workspace/animals"}, "success": True},
        {"tool": "copy_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
    ]

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            # BENIGN interrupt flag
            "max_iterations_exceeded": True,
            # Trace from the specialist's work
            "resume_trace": original_trace
        },
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["animals/", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    # Should have resume_trace, NOT gathered_context
    assert "resume_trace" in result["artifacts"]
    assert result["artifacts"]["resume_trace"] == original_trace
    assert "gathered_context" not in result["artifacts"]

    # Consumer clears the flag
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
            "resume_trace": [
                {"tool": "list_directory", "args": {"path": "/workspace"}, "success": True},
            ]
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
    Issue #114: BENIGN continuation when EI says INCOMPLETE but max_iterations caused it.

    When max_iterations_exceeded=True AND exit_interview_result.is_complete=False,
    this is BENIGN continuation (model was working, ran out of runway), not correction.
    Facilitator should early return with resume_trace.

    The model doesn't need EI feedback - it continues its conversation naturally.
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

    original_trace = [
        {"tool": "copy_file", "args": {"source": "a", "destination": "b"}, "success": True},
    ]

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,  # Model was working
            "exit_interview_result": {
                "is_complete": False,  # EI judged incomplete
                "reasoning": "Files not fully categorized"
            },
            "resume_trace": original_trace
        },
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    # BENIGN continuation - resume_trace, not gathered_context
    assert "resume_trace" in result["artifacts"]
    assert result["artifacts"]["resume_trace"] == original_trace
    assert "gathered_context" not in result["artifacts"]
    assert result["artifacts"]["max_iterations_exceeded"] is False


def test_facilitator_no_wip_summary_without_trace(facilitator):
    """
    Issue #108: No work-in-progress summary if no research trace exists.
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
            # NO research_trace
        },
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Should NOT have work-in-progress summary (no trace to summarize)
    assert "## Work In Progress" not in gathered


def test_facilitator_benign_passes_full_trace(facilitator):
    """
    Issue #114: BENIGN continuation passes full trace, not a summary.

    The model sees its complete conversation history, including the last action.
    No need for a "last action" summary - it's in the trace.
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

    original_trace = [
        {"tool": "read_file", "args": {"path": "/workspace/1.txt"}, "success": True},
        {"tool": "copy_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
    ]

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "max_iterations_exceeded": True,
            "resume_trace": original_trace
        },
        "routing_history": ["project_director"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["file.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Should NOT call filesystem (early return)
        mock_list.assert_not_called()

    # Full trace passed through - model sees its actual conversation
    assert "resume_trace" in result["artifacts"]
    assert result["artifacts"]["resume_trace"] == original_trace
    assert len(result["artifacts"]["resume_trace"]) == 2

    # Last action is in the trace (model sees it naturally)
    last_action = result["artifacts"]["resume_trace"][-1]
    assert last_action["tool"] == "copy_file"
    assert last_action["args"]["source"] == "/workspace/1.txt"
    assert last_action["args"]["destination"] == "/workspace/animals/1.txt"


# =============================================================================
# Issue #114: BENIGN Resume Early Return
# =============================================================================

def test_facilitator_benign_resume_passes_trace_without_context_accumulation(facilitator):
    """
    Issue #114: BENIGN resume should pass trace through without context pollution.

    When max_iterations fires (no exit_interview_result) and prior work exists,
    Facilitator should return early with just the resume_trace - no re-gathering
    context, no accumulation to gathered_context.

    Without this, gathered_context accumulates duplicate directory listings and
    stale EI feedback, polluting the task_prompt that becomes the HumanMessage.
    The model sees garbage in its "goal" and makes different decisions (creates
    "weather" instead of continuing with animals/fruits/colors).

    The fix: early return when resume_trace exists and no exit_interview_result.
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

    # BENIGN state: trace exists, NO exit_interview_result
    original_gathered_context = """### Directory: /workspace/test
- [FILE] /workspace/test/1.txt
- [FILE] /workspace/test/2.txt
- [FILE] /workspace/test/3.txt"""

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "gathered_context": original_gathered_context,
            "max_iterations_exceeded": True,  # BENIGN interrupt flag
            # Prior work trace - this is what should be passed through
            "resume_trace": [
                {"tool": "list_directory", "args": {"path": "/workspace/test"}, "success": True},
                {"tool": "read_file", "args": {"path": "/workspace/test/1.txt"}, "success": True},
                {"tool": "create_directory", "args": {"path": "/workspace/test/animals"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/test/1.txt", "destination": "/workspace/test/animals/1.txt"}, "success": True},
            ]
        },
        "scratchpad": {
            # NO exit_interview_result - this is the BENIGN path
        },
        "routing_history": ["triage_architect", "facilitator_specialist", "router_specialist", "project_director"]
    }

    # Mock _list_directory_via_filesystem_mcp to verify it's NOT called
    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["2.txt", "3.txt", "[DIR] animals"]
        result = facilitator.execute(state)

        # CRITICAL: _list_directory should NOT be called (early return)
        mock_list.assert_not_called()

    # =========================================================================
    # CRITICAL PATTERN: Trace passthrough must be UNMODIFIED
    # The exact data in artifacts["resume_trace"] must pass through unchanged
    # - no transformation, no appending, no filtering.
    # =========================================================================
    assert "resume_trace" in result["artifacts"]
    resume_trace = result["artifacts"]["resume_trace"]

    # Must match the input EXACTLY - same count, same order, same data
    original_trace = state["artifacts"]["resume_trace"]
    assert resume_trace == original_trace, (
        f"resume_trace was modified during passthrough!\n"
        f"Input: {original_trace}\n"
        f"Output: {resume_trace}"
    )

    # =========================================================================
    # CRITICAL PATTERN: Early return should NOT touch gathered_context
    # The result["artifacts"] should only contain resume_trace.
    # =========================================================================
    assert "gathered_context" not in result["artifacts"], (
        "Early return should NOT include gathered_context - it would pollute "
        "the task_prompt. Leave it alone and let LangGraph's dict merge preserve "
        "the original value."
    )

    # =========================================================================
    # PATTERN: Minimal return structure
    # resume_trace + max_iterations_exceeded (consumer clears the flag)
    # =========================================================================
    assert set(result["artifacts"].keys()) == {"resume_trace", "max_iterations_exceeded"}, (
        f"Unexpected artifacts in early return: {result['artifacts'].keys()}"
    )
    # Consumer clears the flag
    assert result["artifacts"]["max_iterations_exceeded"] is False
    assert result["scratchpad"] == {"facilitator_complete": True}, (
        f"Unexpected scratchpad in early return: {result['scratchpad']}"
    )


def test_facilitator_benign_resume_no_early_return_without_trace(facilitator):
    """
    Issue #114: Without prior trace, BENIGN path should NOT early return.

    If max_iterations fired but no trace exists, Facilitator must still gather
    context normally. The early return only applies when resume_trace can be
    assembled (i.e., research_trace_N artifacts exist).
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
            "max_iterations_exceeded": True,  # BENIGN flag
            # NO resume_trace - no prior work exists
        },
        "scratchpad": {},  # NO exit_interview_result
        "routing_history": []
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # _list_directory SHOULD be called (no early return)
        mock_list.assert_called_once()

    # Result should have gathered_context (normal execution)
    assert "gathered_context" in result["artifacts"]
    assert "### Directory: /workspace/test" in result["artifacts"]["gathered_context"]

    # resume_trace should NOT be in result (no trace to assemble)
    # Check both possible locations
    assert "resume_trace" not in result.get("artifacts", {}) or result["artifacts"].get("resume_trace") is None


def test_facilitator_no_early_return_when_exit_interview_result_present(facilitator):
    """
    Issue #114: When exit_interview_result is present, NO early return.
    Issue #121: EI feedback NOT added to gathered_context (Router uses recommended_specialists).

    Exit Interview retry path should NOT early return - it needs to re-gather context.
    The early return is specifically for BENIGN (max_iterations, no EI result) continuation.
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
            "resume_trace": [
                {"tool": "list_directory", "args": {"path": "/workspace/test"}, "success": True},
            ],
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
    Issue #114: BENIGN continuation when EI says INCOMPLETE but max_iterations was the cause.

    When:
    - max_iterations_exceeded: True (model was working, ran out of runway)
    - exit_interview_result.is_complete: False (EI correctly judged work incomplete)

    This is CONTINUATION, not CORRECTION. The model was doing the right thing,
    it just needs more iterations. Pass the resume_trace through.

    Before fix: EI cleared max_iterations_exceeded, Facilitator saw EI result,
    treated it as correction cycle, PD started from zero.

    After fix: Facilitator checks max_iterations_exceeded BEFORE deciding.
    If True + INCOMPLETE, it's BENIGN continuation.
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

    original_trace = [
        {"tool": "list_directory", "args": {"path": "/workspace/test"}, "success": True},
        {"tool": "read_file", "args": {"path": "/workspace/test/1.txt"}, "success": True},
        {"tool": "create_directory", "args": {"path": "/workspace/test/animals"}, "success": True},
    ]

    state = {
        "artifacts": {
            "context_plan": plan.model_dump(),
            "resume_trace": original_trace,
            # KEY: Both flags present - this is BENIGN+INCOMPLETE
            "max_iterations_exceeded": True,  # Model was working
            "exit_interview_result": {
                "is_complete": False,  # EI correctly judged incomplete
                "reasoning": "Only 1 of 6 files categorized",
                "missing_elements": "5 files still need categorization",
                "recommended_specialists": ["project_director"],
                "return_control": "accumulate"
            }
        },
        "scratchpad": {},
        "routing_history": ["project_director", "exit_interview_specialist"]
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["1.txt", "2.txt", "3.txt"]
        result = facilitator.execute(state)

        # CRITICAL: Early return - should NOT re-gather context
        mock_list.assert_not_called()

    # Should return resume_trace for continuation
    assert "resume_trace" in result["artifacts"]
    assert result["artifacts"]["resume_trace"] == original_trace

    # Should NOT include gathered_context (early return)
    assert "gathered_context" not in result["artifacts"]

    # Should clear max_iterations_exceeded (consumer clears flag)
    assert result["artifacts"]["max_iterations_exceeded"] is False

    # Should mark facilitator complete
    assert result["scratchpad"] == {"facilitator_complete": True}