"""
Integration tests for external filesystem MCP container.

Validates the @modelcontextprotocol/server-filesystem container is accessible
and all operations used by specialists work correctly.

Run with: docker exec langgraph-app pytest app/tests/integration/test_filesystem_mcp.py -v

Prerequisites:
- filesystem-mcp container running (docker compose --profile filesystem up)
- Config: mcp.external_mcp.services.filesystem.enabled = true

Note: Uses shared MCP fixtures from conftest.py (connected_filesystem_client).
"""
import pytest
from pathlib import Path

from app.tests.helpers import (
    folder_of_files_with_content,
    unique_test_folder,
    cleanup_folder,
)


# =============================================================================
# LOCAL FIXTURES
# =============================================================================

@pytest.fixture
def test_folder():
    """Create unique test folder, cleanup after."""
    folder = unique_test_folder("mcp_test")
    yield folder
    cleanup_folder(folder)


# =============================================================================
# Connection Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_filesystem_mcp_connection(connected_filesystem_client):
    """Verify connection to filesystem MCP container succeeds."""
    assert connected_filesystem_client.is_connected("filesystem")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_filesystem_mcp_list_tools(connected_filesystem_client):
    """Verify filesystem MCP exposes expected tools."""
    tools = await connected_filesystem_client.list_tools("filesystem")

    # Core tools we need
    expected_tools = [
        "list_directory",
        "read_file",
        "write_file",
        "create_directory",
        "move_file",
        "get_file_info",
    ]

    for tool in expected_tools:
        assert tool in tools, f"Missing tool: {tool}. Available: {tools}"


# =============================================================================
# Operation Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_directory(connected_filesystem_client, test_folder):
    """Test list_directory returns file names."""
    # Create test files via native Python (test setup, not testing MCP write)
    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {
            "alpha.txt": "content alpha",
            "bravo.txt": "content bravo",
        }
    )

    # MCP path uses /workspace mount (filesystem-mcp container mount point)
    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}"

    result = await connected_filesystem_client.call_tool(
        "filesystem",
        "list_directory",
        {"path": mcp_path}
    )

    # Extract text from result
    text = _extract_text(result)

    assert "alpha.txt" in text, f"Expected alpha.txt in listing. Got: {text}"
    assert "bravo.txt" in text, f"Expected bravo.txt in listing. Got: {text}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_file(connected_filesystem_client, test_folder):
    """Test read_file returns file contents."""
    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {"test_read.txt": "Hello from test file"}
    )

    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}/test_read.txt"

    result = await connected_filesystem_client.call_tool(
        "filesystem",
        "read_file",
        {"path": mcp_path}
    )

    text = _extract_text(result)
    assert "Hello from test file" in text, f"Content mismatch. Got: {text}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_write_file(connected_filesystem_client, test_folder):
    """Test write_file creates file with content."""
    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}/test_write.txt"

    await connected_filesystem_client.call_tool(
        "filesystem",
        "write_file",
        {
            "path": mcp_path,
            "content": "Written via MCP"
        }
    )

    # Verify via native Python read
    local_path = test_folder / "test_write.txt"
    assert local_path.exists(), f"File not created at {local_path}"
    assert local_path.read_text() == "Written via MCP"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_directory(connected_filesystem_client, test_folder):
    """Test create_directory creates a single directory.

    Note: Filesystem MCP doesn't support recursive mkdir.
    Parent directory must already exist.
    """
    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}/newdir"

    await connected_filesystem_client.call_tool(
        "filesystem",
        "create_directory",
        {"path": mcp_path}
    )

    # Verify via native Python
    local_path = test_folder / "newdir"
    assert local_path.exists(), f"Directory not created at {local_path}"
    assert local_path.is_dir()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_move_file(connected_filesystem_client, test_folder):
    """Test move_file renames/moves files."""
    # Create source file
    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {"source.txt": "Content to move"}
    )

    base_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}"

    await connected_filesystem_client.call_tool(
        "filesystem",
        "move_file",
        {
            "source": f"{base_path}/source.txt",
            "destination": f"{base_path}/destination.txt"
        }
    )

    # Verify via native Python
    assert not (test_folder / "source.txt").exists(), "Source file should be removed"
    assert (test_folder / "destination.txt").exists(), "Destination file should exist"
    assert (test_folder / "destination.txt").read_text() == "Content to move"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_file_info(connected_filesystem_client, test_folder):
    """Test get_file_info returns metadata."""
    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {"info_test.txt": "Some content"}
    )

    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}/info_test.txt"

    result = await connected_filesystem_client.call_tool(
        "filesystem",
        "get_file_info",
        {"path": mcp_path}
    )

    text = _extract_text(result)
    # Should contain some metadata - file name, size, etc.
    assert "info_test.txt" in text or "file" in text.lower(), f"Expected file info. Got: {text}"


# =============================================================================
# Sync Bridge Tests (GitHub #28)
# =============================================================================
#
# Note: These tests are skipped because sync_call_external_mcp deadlocks when
# called from within an async test. The sync bridge uses run_coroutine_threadsafe
# to schedule on _main_loop, then blocks on future.result(). In pytest-asyncio,
# the async test runs in the same thread that owns _main_loop, causing deadlock.
#
# In production this works because GraphBuilder initializes MCP in async context
# while specialists run synchronously in a different thread/context.
#
# The sync bridge functionality is validated in production workflows and by
# the FileOperationDispatcher tests (which use dispatch_sync).
# =============================================================================

@pytest.mark.skip(reason="Sync bridge deadlocks in pytest-asyncio context (same-thread event loop)")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_bridge_list_directory(connected_filesystem_client, test_folder):
    """Test sync_call_external_mcp works (validates fix for GitHub #28).

    SKIPPED: Cannot test sync bridge from async test context.
    See comment block above for explanation.
    """
    from app.src.mcp.external_client import sync_call_external_mcp

    # Create test files
    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {"sync_test.txt": "sync bridge test content"}
    )

    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}"

    # Call via sync bridge (this is what specialists use)
    result = sync_call_external_mcp(
        connected_filesystem_client,
        "filesystem",
        "list_directory",
        {"path": mcp_path}
    )

    text = _extract_text(result)
    assert "sync_test.txt" in text, f"Expected sync_test.txt in listing. Got: {text}"


@pytest.mark.skip(reason="Sync bridge deadlocks in pytest-asyncio context (same-thread event loop)")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sync_bridge_read_file(connected_filesystem_client, test_folder):
    """Test sync bridge read_file operation.

    SKIPPED: Cannot test sync bridge from async test context.
    See comment block above for explanation.
    """
    from app.src.mcp.external_client import sync_call_external_mcp

    folder_of_files_with_content(
        str(test_folder.relative_to(Path("workspace").resolve())),
        {"sync_read.txt": "Hello from sync bridge"}
    )

    mcp_path = f"/workspace/{test_folder.relative_to(Path('workspace').resolve())}/sync_read.txt"

    result = sync_call_external_mcp(
        connected_filesystem_client,
        "filesystem",
        "read_file",
        {"path": mcp_path}
    )

    text = _extract_text(result)
    assert "Hello from sync bridge" in text, f"Content mismatch. Got: {text}"


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_read_nonexistent_file_raises(connected_filesystem_client):
    """Test reading nonexistent file raises RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        await connected_filesystem_client.call_tool(
            "filesystem",
            "read_file",
            {"path": "/workspace/nonexistent_file_abc123.txt"}
        )

    assert "fail" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_nonexistent_directory_raises(connected_filesystem_client):
    """Test listing nonexistent directory raises RuntimeError."""
    with pytest.raises(RuntimeError) as exc_info:
        await connected_filesystem_client.call_tool(
            "filesystem",
            "list_directory",
            {"path": "/workspace/nonexistent_dir_abc123"}
        )

    assert "fail" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_text(result) -> str:
    """Extract text content from MCP result object."""
    if result is None:
        return ""

    if hasattr(result, 'content'):
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            first = content[0]
            if hasattr(first, 'text'):
                return first.text
            return str(first)
        return str(content)

    return str(result)
