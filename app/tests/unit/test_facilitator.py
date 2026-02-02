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


def test_facilitator_prior_work_summary_included_in_context(facilitator):
    """
    ADR-ROADMAP-001: Facilitator summarizes research_trace artifacts for continuity.

    When research_trace_N artifacts exist, Facilitator appends a summary so
    downstream specialists know what was already done.
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
            "research_trace_0": [
                {"tool": "create_directory", "args": {"path": "/workspace/animals"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/2.txt", "destination": "/workspace/animals/2.txt"}, "success": False, "error": "Hit iteration limit"},
            ]
        }
    }

    with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
        mock_list.return_value = ["3.txt", "[DIR] animals"]
        result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]

    # Prior work summary should be included
    assert "### Previous Work" in gathered
    assert "do not repeat these operations" in gathered

    # Tool signatures should be summarized
    assert "create_directory ✓" in gathered
    assert "move_file ✓" in gathered
    assert "move_file ✗" in gathered  # Failed operation

    # Next step guidance should be present
    assert "Proceed to the next phase" in gathered