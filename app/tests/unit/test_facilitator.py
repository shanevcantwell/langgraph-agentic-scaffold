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
