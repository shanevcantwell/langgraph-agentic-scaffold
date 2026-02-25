"""
Facilitator core context gathering tests: actions, directory listing, MCP, errors.

Retry context tests are in test_facilitator_retry.py.
BENIGN interrupt tests are in test_facilitator_benign.py.
"""
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.facilitator_specialist import FacilitatorSpecialist


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
    """#223: RESEARCH action calls webfetch-mcp web_search via external MCP."""
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "LangGraph", "description": "Search", "strategy": None}
            ],
            "triage_reasoning": "Need info",
        },
        "artifacts": {}
    }

    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("Result 1: LangGraph overview\nResult 2: LangGraph tutorial")
        result = facilitator.execute(state)

    # Assert webfetch was called with correct params
    mock_sync.assert_called_once_with(
        facilitator.external_mcp_client,
        "webfetch",
        "web_search",
        {"query": "LangGraph"},
    )
    assert "### Research: LangGraph" in result["artifacts"]["gathered_context"]
    assert "LangGraph overview" in result["artifacts"]["gathered_context"]

def test_facilitator_executes_read_file_action(facilitator):
    # Arrange
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "read_file", "target": "/path/to/file", "description": "Read", "strategy": None}
            ],
            "triage_reasoning": "Need file",
        },
        "artifacts": {}
    }

    # Act - Mock external MCP call (ADR-CORE-035: file ops via filesystem container)
    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("File content")
        result = facilitator.execute(state)

    # Assert
    assert "### File: /path/to/file" in result["artifacts"]["gathered_context"]
    assert "File content" in result["artifacts"]["gathered_context"]

def test_facilitator_handles_missing_plan(facilitator):
    """No triage_actions and no artifacts — Facilitator still returns gathered_context."""
    state = {"artifacts": {}, "scratchpad": {}}
    result = facilitator.execute(state)
    assert "gathered_context" in result.get("artifacts", {})

def test_facilitator_research_webfetch_unavailable(facilitator):
    """#223: When webfetch MCP is unavailable, RESEARCH degrades gracefully."""
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "LangGraph", "description": "Search", "strategy": None}
            ],
            "triage_reasoning": "Need info",
        },
        "artifacts": {}
    }

    # webfetch not connected (filesystem still is)
    facilitator.external_mcp_client.is_connected.side_effect = lambda svc: svc != "webfetch"

    result = facilitator.execute(state)

    assert "### Research: LangGraph" in result["artifacts"]["gathered_context"]
    assert "Webfetch MCP unavailable" in result["artifacts"]["gathered_context"]
    facilitator.mcp_client.call.assert_not_called()

def test_facilitator_reads_artifact_instead_of_file_for_uploaded_image(facilitator):
    """Test that Facilitator retrieves in-memory artifacts instead of trying to read from filesystem."""
    # Arrange
    image_data = "data:image/png;base64,iVBORw0KGgoAAAANS..."
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "read_file", "target": "/artifacts/image.png", "description": "Read image", "strategy": None}
            ],
            "triage_reasoning": "Need to analyze uploaded image",
        },
        "artifacts": {
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
    image_data = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA..."
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "read_file", "target": "uploaded_image.png", "description": "Read image", "strategy": None}
            ],
            "triage_reasoning": "Need to analyze uploaded image",
        },
        "artifacts": {
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
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "read_file", "target": "config.yaml", "description": "Read config", "strategy": None}
            ],
            "triage_reasoning": "Need actual file from workspace",
        },
        "artifacts": {
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
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "sort_by_contents", "description": "List files to sort", "strategy": None}
            ],
            "triage_reasoning": "Need to see directory contents",
        },
        "artifacts": {}
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
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "workspace", "description": "List workspace", "strategy": None}
            ],
            "triage_reasoning": "Need to see directory contents",
        },
        "artifacts": {}
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
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "summarize", "target": "This is a very long document with many details...", "description": "Summarize the content", "strategy": None}
            ],
            "triage_reasoning": "Need summary",
        },
        "artifacts": {}
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
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "summarize", "target": "/workspace/long_document.md", "description": "Summarize the document", "strategy": None}
            ],
            "triage_reasoning": "Summarize a file",
        },
        "artifacts": {}
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

    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "ask_user", "target": "What file format do you prefer?", "description": "Clarify user preference", "strategy": None}
            ],
            "triage_reasoning": "Need user clarification",
        },
        "artifacts": {}
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
        # question_text uses action.target (the actual question to ask the user)
        assert "what file format do you prefer?" in call_payload["question"].lower()

    # No MCP calls should have been made (ASK_USER uses interrupt, not MCP)
    facilitator.mcp_client.call.assert_not_called()

    # User's clarification should be in gathered_context
    assert "I prefer JSON format" in result["artifacts"]["gathered_context"]
    assert "User Clarification" in result["artifacts"]["gathered_context"]


def test_facilitator_propagates_graph_interrupt_for_ask_user(facilitator):
    """
    BUG FIX: GraphInterrupt raised by interrupt() must NOT be caught by
    the except Exception handler. It must propagate to the LangGraph runner
    for the pause/resume mechanism to work.

    The existing test (test_facilitator_handles_ask_user_action_via_interrupt)
    simulates the RESUME path where interrupt() returns a value.
    This test simulates the FIRST invocation where interrupt() raises.
    """
    from unittest.mock import patch
    from langgraph.errors import GraphInterrupt

    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "ask_user", "target": "What tone should the backronym have?", "description": "Clarify desired tone", "strategy": None}
            ],
            "triage_reasoning": "Need user clarification",
        },
        "artifacts": {}
    }

    with patch("langgraph.types.interrupt", side_effect=GraphInterrupt(("test",))):
        with pytest.raises(GraphInterrupt):
            facilitator.execute(state)


def test_facilitator_interrupt_propagates_with_prior_actions(facilitator):
    """
    When a plan has RESEARCH then ASK_USER, the interrupt must still propagate.
    #223: RESEARCH calls webfetch-mcp, ASK_USER's GraphInterrupt must still
    bubble up rather than being caught as an error.
    """
    from unittest.mock import patch
    from langgraph.errors import GraphInterrupt

    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "topic", "description": "Research first", "strategy": None},
                {"type": "ask_user", "target": "Clarify?", "description": "Need input", "strategy": None},
            ],
            "triage_reasoning": "Research then ask user",
        },
        "artifacts": {}
    }

    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("Search results for topic")
        with patch("langgraph.types.interrupt", side_effect=GraphInterrupt(("test",))):
            with pytest.raises(GraphInterrupt):
                facilitator.execute(state)

    # RESEARCH called webfetch, then ASK_USER raised GraphInterrupt
    mock_sync.assert_called_once()


def test_facilitator_skips_ask_user_on_ei_retry(facilitator):
    """
    On EI retry (exit_interview_result present), Facilitator skips ask_user actions.

    The user already clarified in the first pass. Re-asking the same question is
    wrong — EI feedback guides the retry, not a repeated clarification request.
    """
    from unittest.mock import patch

    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List workspace", "strategy": None},
                {"type": "ask_user", "target": "What kind of website?", "description": "Clarify website type", "strategy": None},
            ],
            "triage_reasoning": "Need clarification",
        },
        "artifacts": {
            "exit_interview_result": {
                "is_complete": False,
                "reasoning": "www2 directory does not exist",
                "missing_elements": "www2 directory and required files",
                "recommended_specialists": ["project_director"],
            }
        },
        "routing_history": ["web_builder", "exit_interview_specialist"]
    }

    # interrupt should NOT be called — ask_user is skipped on retry
    with patch("langgraph.types.interrupt") as mock_interrupt:
        with patch.object(facilitator, '_list_directory_via_filesystem_mcp') as mock_list:
            mock_list.return_value = ["file.txt"]
            result = facilitator.execute(state)

        mock_interrupt.assert_not_called()

    # Directory listing should still execute (non-ask_user actions run normally)
    assert "file.txt" in result["artifacts"]["gathered_context"]
    # No user clarification section (ask_user was skipped)
    assert "User Clarification" not in result["artifacts"]["gathered_context"]


def test_facilitator_executes_multiple_actions(facilitator):
    """
    Per FACILITATOR.md: Facilitator processes all actions in the plan sequentially,
    joining results with double newlines.
    #223: Both RESEARCH actions call webfetch-mcp web_search.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "topic1", "description": "Search topic1", "strategy": None},
                {"type": "research", "target": "topic2", "description": "Search topic2", "strategy": None},
            ],
            "triage_reasoning": "Need multiple context sources",
        },
        "artifacts": {}
    }

    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.return_value = _make_mcp_result("Search results")
        result = facilitator.execute(state)

    # webfetch called twice (once per RESEARCH action)
    assert mock_sync.call_count == 2

    # Both results should appear in gathered_context
    gathered = result["artifacts"]["gathered_context"]
    assert "### Research: topic1" in gathered
    assert "### Research: topic2" in gathered
    assert "\n\n" in gathered  # Sections joined with double newline


def test_facilitator_filesystem_unavailable_graceful_degradation(facilitator):
    """
    Per FACILITATOR.md: If filesystem MCP is unavailable, Facilitator includes
    "[Filesystem service unavailable]" message and continues.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "read_file", "target": "/path/to/file", "description": "Read file", "strategy": None}
            ],
            "triage_reasoning": "Need file",
        },
        "artifacts": {}
    }

    # Mock filesystem as unavailable
    facilitator.external_mcp_client.is_connected.return_value = False

    result = facilitator.execute(state)

    # Should show unavailable message, not error
    gathered = result["artifacts"]["gathered_context"]
    assert "### File: /path/to/file" in gathered
    assert "[Filesystem service unavailable]" in gathered


def test_facilitator_directory_listing_filesystem_unavailable(facilitator):
    """
    Per FACILITATOR.md: LIST_DIRECTORY also gracefully handles filesystem unavailability.
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "list_directory", "target": "/workspace", "description": "List", "strategy": None}
            ],
            "triage_reasoning": "List directory",
        },
        "artifacts": {}
    }

    facilitator.external_mcp_client.is_connected.return_value = False

    result = facilitator.execute(state)

    gathered = result["artifacts"]["gathered_context"]
    assert "### Directory: /workspace" in gathered
    assert "[Filesystem service unavailable]" in gathered


def test_facilitator_handles_empty_triage_actions(facilitator):
    """
    When triage_actions is empty (Triage PASS), Facilitator assembles context
    from available artifacts without executing MCP actions.
    """
    state = {
        "scratchpad": {
            "triage_actions": [],  # Empty = Triage PASS
            "triage_reasoning": "No actions",
        },
        "artifacts": {
            "task_plan": {"plan_summary": "Test strategy", "execution_steps": ["Step 1"]}
        }
    }

    result = facilitator.execute(state)

    assert "gathered_context" in result.get("artifacts", {})
    assert "Test strategy" in result["artifacts"]["gathered_context"]


def test_facilitator_continues_after_action_error(facilitator):
    """
    Per FACILITATOR.md: Individual action failures don't halt the entire plan.
    Error is logged and next action continues.
    #223: RESEARCH calls webfetch (fails), SUMMARIZE calls internal MCP (succeeds).
    """
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "failing_query", "description": "Will fail", "strategy": None},
                {"type": "summarize", "target": "some text to summarize", "description": "Will succeed", "strategy": None},
            ],
            "triage_reasoning": "Multiple actions with mixed types",
        },
        "artifacts": {}
    }

    facilitator.mcp_client.call.return_value = "Summarized text"

    with patch('app.src.specialists.facilitator_specialist.sync_call_external_mcp') as mock_sync:
        mock_sync.side_effect = Exception("SearXNG connection refused")
        result = facilitator.execute(state)

    # RESEARCH failed → error captured, SUMMARIZE succeeded
    gathered = result["artifacts"]["gathered_context"]
    assert "### Error: failing_query" in gathered
    assert "SearXNG connection refused" in gathered
    assert "### Summary:" in gathered

