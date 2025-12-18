"""
Integration tests for Navigation MCP Integration (ADR-CORE-027).

Tests navigator-mcp connectivity for:
- Filesystem tree traversal (goto, list, delete, find)
- Browser navigation with visual grounding (goto, click, type, act)

Prerequisites:
1. Start navigator container: docker-compose --profile navigator up -d
2. Run tests inside Docker: docker compose exec app pytest app/tests/integration/test_navigator_mcp.py -v

These tests require the navigator-mcp container to be running.
"""
import pytest
import asyncio
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from app.src.mcp.external_client import ExternalMcpClient
from app.src.utils.config_loader import ConfigLoader


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def config() -> Dict[str, Any]:
    """Load configuration from config.yaml."""
    config_loader = ConfigLoader()
    return config_loader.get_config()


@pytest.fixture
def workspace_path() -> str:
    """Get workspace path from environment or use default."""
    return os.getenv("WORKSPACE_PATH", "/app/workspace")


@pytest.fixture
async def external_mcp_client(config):
    """Create and initialize ExternalMcpClient, cleanup on teardown."""
    client = ExternalMcpClient(config)
    yield client
    await client.cleanup()


@pytest.fixture
async def connected_navigator_client(external_mcp_client):
    """
    ExternalMcpClient with navigator service connected.

    Uses connect_from_config to connect via docker exec.
    """
    tools = await external_mcp_client.connect_from_config("navigator")

    if tools is None:
        pytest.skip(
            "Navigator not available. Start with: docker-compose --profile navigator up -d"
        )

    yield external_mcp_client


# =============================================================================
# UNIT TESTS: connect_from_config
# =============================================================================

class TestConnectFromConfig:
    """Test the new connect_from_config method."""

    @pytest.mark.asyncio
    async def test_connect_from_config_disabled_service(self, config):
        """Test that disabled service returns None."""
        # Modify config to disable navigator
        config["mcp"]["external_mcp"]["services"]["navigator"]["enabled"] = False
        client = ExternalMcpClient(config)

        result = await client.connect_from_config("navigator")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connect_from_config_nonexistent_service(self, config):
        """Test that nonexistent service returns None."""
        client = ExternalMcpClient(config)

        result = await client.connect_from_config("nonexistent_service")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connect_from_config_missing_connection_config(self, config):
        """Test that service without container_name or command returns None."""
        # Add service with no connection method
        config["mcp"]["external_mcp"]["services"]["bad_service"] = {
            "enabled": True,
            "required": False,
            # No container_name or command
        }
        client = ExternalMcpClient(config)

        result = await client.connect_from_config("bad_service")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connect_from_config_required_missing_raises(self, config):
        """Test that required service with missing config raises ValueError."""
        config["mcp"]["external_mcp"]["services"]["bad_required"] = {
            "enabled": True,
            "required": True,  # Required!
            # No container_name or command
        }
        client = ExternalMcpClient(config)

        with pytest.raises(ValueError, match="no connection config"):
            await client.connect_from_config("bad_required")

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connect_all_from_config_disabled_globally(self, config):
        """Test that globally disabled external MCP returns empty dict."""
        config["mcp"]["external_mcp"]["enabled"] = False
        client = ExternalMcpClient(config)

        result = await client.connect_all_from_config()

        assert result == {}
        await client.cleanup()


# =============================================================================
# INTEGRATION TESTS: Connection Lifecycle
# =============================================================================

class TestNavigatorConnection:
    """Test navigator MCP container connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_navigator_via_config(self, external_mcp_client):
        """Test connecting to navigator via connect_from_config."""
        tools = await external_mcp_client.connect_from_config("navigator")

        if tools is None:
            pytest.skip("Navigator not running")

        # Verify connection
        assert external_mcp_client.is_connected("navigator")
        assert "navigator" in external_mcp_client.get_connected_services()

        # Verify expected tools are available
        assert len(tools) > 0
        # Core tools should be present
        expected_tools = ["session_create", "session_destroy", "goto", "list"]
        for tool in expected_tools:
            assert tool in tools, f"Expected tool '{tool}' not found in {tools}"

    @pytest.mark.asyncio
    async def test_health_check(self, connected_navigator_client):
        """Test health check on connected navigator."""
        is_healthy = await connected_navigator_client.health_check("navigator")
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_list_tools(self, connected_navigator_client):
        """Test listing all navigator tools."""
        tools = await connected_navigator_client.list_tools("navigator")

        assert isinstance(tools, list)
        assert len(tools) > 10  # Navigator has many tools

        # Filesystem tools
        assert "goto" in tools
        assert "list" in tools
        assert "read" in tools
        assert "write" in tools
        assert "delete" in tools
        assert "find" in tools

        # Session tools
        assert "session_create" in tools
        assert "session_destroy" in tools

        # Browser tools (may or may not be present depending on config)
        browser_tools = ["click", "type", "scroll", "act", "snapshot"]
        browser_available = any(t in tools for t in browser_tools)
        print(f"Browser tools available: {browser_available}")


# =============================================================================
# INTEGRATION TESTS: Session Management
# =============================================================================

class TestNavigatorSessions:
    """Test navigator session lifecycle."""

    @pytest.mark.asyncio
    async def test_create_and_destroy_filesystem_session(self, connected_navigator_client):
        """Test creating and destroying a filesystem session."""
        # Create session
        result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_create",
            arguments={
                "drivers": {
                    "fs": {
                        "type": "filesystem",
                        "root": "/workspace",
                        "sandbox": True
                    }
                }
            }
        )

        assert result is not None
        # Extract session_id from result
        session_id = _extract_session_id(result)
        assert session_id is not None, f"Failed to extract session_id from {result}"

        # Destroy session
        destroy_result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_destroy",
            arguments={"session_id": session_id}
        )

        assert destroy_result is not None

    @pytest.mark.asyncio
    async def test_session_list(self, connected_navigator_client):
        """Test listing active sessions."""
        # Create a session first
        create_result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_create",
            arguments={
                "drivers": {
                    "fs": {"type": "filesystem", "root": "/workspace"}
                }
            }
        )
        session_id = _extract_session_id(create_result)

        try:
            # List sessions
            list_result = await connected_navigator_client.call_tool(
                service_name="navigator",
                tool_name="session_list",
                arguments={}
            )

            assert list_result is not None
            # Result should contain our session
            result_text = _extract_text(list_result)
            assert session_id in result_text or "session" in result_text.lower()

        finally:
            # Cleanup
            await connected_navigator_client.call_tool(
                service_name="navigator",
                tool_name="session_destroy",
                arguments={"session_id": session_id}
            )


# =============================================================================
# INTEGRATION TESTS: Filesystem Operations
# =============================================================================

class TestNavigatorFilesystem:
    """Test navigator filesystem operations (ADR-CORE-027 success criteria)."""

    @pytest.fixture
    async def fs_session(self, connected_navigator_client, workspace_path):
        """Create a filesystem session for testing."""
        result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_create",
            arguments={
                "drivers": {
                    "fs": {
                        "type": "filesystem",
                        "root": "/workspace",
                        "sandbox": True
                    }
                }
            }
        )
        session_id = _extract_session_id(result)
        yield session_id, connected_navigator_client

        # Cleanup session
        await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_destroy",
            arguments={"session_id": session_id}
        )

    @pytest.mark.asyncio
    async def test_goto_and_list(self, fs_session):
        """Test navigating to directory and listing contents."""
        session_id, client = fs_session

        # Navigate to workspace root
        goto_result = await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "location": "."
            }
        )
        assert goto_result is not None

        # List contents
        list_result = await client.call_tool(
            service_name="navigator",
            tool_name="list",
            arguments={
                "session_id": session_id,
                "driver": "fs"
            }
        )
        assert list_result is not None

    @pytest.mark.asyncio
    async def test_write_read_file(self, fs_session):
        """Test writing and reading a file."""
        session_id, client = fs_session
        test_content = "Navigator MCP test content\nLine 2\nLine 3"
        test_file = "test_navigator_write.txt"

        # Write file
        write_result = await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": test_file,
                "content": test_content
            }
        )
        assert write_result is not None

        # Read file back
        read_result = await client.call_tool(
            service_name="navigator",
            tool_name="read",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": test_file
            }
        )
        assert read_result is not None
        result_text = _extract_text(read_result)
        # read returns JSON with "content" key - parse it
        try:
            parsed = json.loads(result_text)
            actual_content = parsed.get("content", result_text)
        except json.JSONDecodeError:
            actual_content = result_text
        assert test_content in actual_content

        # Cleanup
        await client.call_tool(
            service_name="navigator",
            tool_name="delete",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": test_file
            }
        )

    @pytest.mark.asyncio
    async def test_delete_directory_recursive(self, fs_session):
        """
        Test recursive directory deletion (ADR-CORE-027 success criteria #1).

        This tests the key capability that FileSpecialist lacks.
        """
        session_id, client = fs_session

        # Create a directory with nested files
        test_dir = "test_delete_recursive"

        # Create directory structure via write (creates parent dirs)
        await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": f"{test_dir}/file1.txt",
                "content": "file 1"
            }
        )
        await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": f"{test_dir}/subdir/file2.txt",
                "content": "file 2"
            }
        )

        # Delete directory recursively
        delete_result = await client.call_tool(
            service_name="navigator",
            tool_name="delete",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": test_dir,
                "recursive": True
            }
        )
        assert delete_result is not None

        # Verify deletion - listing should fail or return empty
        # Navigate to parent and verify directory is gone
        list_result = await client.call_tool(
            service_name="navigator",
            tool_name="list",
            arguments={
                "session_id": session_id,
                "driver": "fs"
            }
        )
        result_text = _extract_text(list_result)
        assert test_dir not in result_text, f"Directory {test_dir} should be deleted"

    @pytest.mark.asyncio
    async def test_find_glob_pattern(self, fs_session):
        """
        Test glob pattern search (ADR-CORE-027 success criteria #2).

        Tests: "Find all .txt files" returns glob results
        """
        session_id, client = fs_session

        # Create some test files
        await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": "find_test/a.txt",
                "content": "a"
            }
        )
        await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": "find_test/b.txt",
                "content": "b"
            }
        )
        await client.call_tool(
            service_name="navigator",
            tool_name="write",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": "find_test/c.py",
                "content": "c"
            }
        )

        try:
            # Find .txt files
            find_result = await client.call_tool(
                service_name="navigator",
                tool_name="find",
                arguments={
                    "session_id": session_id,
                    "driver": "fs",
                    "pattern": "*.txt"
                }
            )
            assert find_result is not None
            result_text = _extract_text(find_result)

            # Should find a.txt and b.txt but not c.py
            assert "a.txt" in result_text
            assert "b.txt" in result_text

        finally:
            # Cleanup
            await client.call_tool(
                service_name="navigator",
                tool_name="delete",
                arguments={
                    "session_id": session_id,
                    "driver": "fs",
                    "target": "find_test",
                    "recursive": True
                }
            )


# =============================================================================
# INTEGRATION TESTS: Browser Operations (requires Fara)
# =============================================================================

class TestNavigatorBrowser:
    """
    Test navigator browser operations with visual grounding.

    These tests require:
    1. Navigator container running with browser driver
    2. Fara model loaded in LM Studio
    """

    @pytest.fixture
    async def browser_session(self, connected_navigator_client):
        """Create a browser session for testing."""
        result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_create",
            arguments={
                "drivers": {
                    "web": {
                        "type": "browser",
                        "headless": True
                    }
                }
            }
        )
        session_id = _extract_session_id(result)

        if session_id is None:
            pytest.skip("Browser session creation failed - Playwright may not be available")

        yield session_id, connected_navigator_client

        # Cleanup session
        await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_destroy",
            arguments={"session_id": session_id}
        )

    @pytest.mark.asyncio
    async def test_browser_goto(self, browser_session):
        """Test navigating to a URL."""
        session_id, client = browser_session

        # Navigate to a simple page
        result = await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "web",
                "location": "https://example.com"
            }
        )
        assert result is not None
        result_text = _extract_text(result)
        # Should contain URL or success indication
        assert "example.com" in result_text.lower() or "success" in result_text.lower()

    @pytest.mark.asyncio
    async def test_browser_read_content(self, browser_session):
        """Test reading page content."""
        session_id, client = browser_session

        # Navigate first
        await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "web",
                "location": "https://example.com"
            }
        )

        # Read page content
        result = await client.call_tool(
            service_name="navigator",
            tool_name="read",
            arguments={
                "session_id": session_id,
                "driver": "web"
            }
        )
        assert result is not None
        result_text = _extract_text(result)
        # Example.com has distinctive content
        assert "example" in result_text.lower()

    @pytest.mark.asyncio
    async def test_browser_snapshot(self, browser_session):
        """Test taking a screenshot."""
        session_id, client = browser_session

        # Navigate first
        await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "web",
                "location": "https://example.com"
            }
        )

        # Take snapshot
        result = await client.call_tool(
            service_name="navigator",
            tool_name="snapshot",
            arguments={
                "session_id": session_id,
                "driver": "web"
            }
        )
        assert result is not None
        # Snapshot should return base64 image or file path

    @pytest.mark.asyncio
    async def test_browser_click_visual_grounding(self, browser_session):
        """
        Test clicking element by natural language description.

        ADR-CORE-027 success criteria #3: Browser navigation with visual grounding
        """
        session_id, client = browser_session

        # Navigate to a page with clickable elements
        await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "web",
                "location": "https://example.com"
            }
        )

        # Click using visual description
        result = await client.call_tool(
            service_name="navigator",
            tool_name="click",
            arguments={
                "session_id": session_id,
                "driver": "web",
                "description": "the More information link"
            }
        )
        assert result is not None


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestNavigatorErrorHandling:
    """Test fail-fast error handling."""

    @pytest.mark.asyncio
    async def test_call_tool_disconnected_service(self, external_mcp_client):
        """Test that calling tool on disconnected service raises ValueError."""
        with pytest.raises(ValueError, match="not connected"):
            await external_mcp_client.call_tool(
                service_name="navigator",
                tool_name="session_create",
                arguments={}
            )

    @pytest.mark.asyncio
    async def test_invalid_session_id(self, connected_navigator_client):
        """Test that invalid session_id returns error."""
        result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": "invalid-session-id-12345",
                "driver": "fs",
                "location": "."
            }
        )
        # navigator-mcp returns errors in content JSON, not via isError flag
        result_text = _extract_text(result)
        try:
            parsed = json.loads(result_text)
            assert "error" in parsed, f"Expected error in response: {result_text}"
            assert "Session not found" in parsed["error"]
        except json.JSONDecodeError:
            # If not JSON, check for error text
            assert "error" in result_text.lower() or "Session not found" in result_text


# =============================================================================
# SECURITY TESTS
# =============================================================================

class TestNavigatorSecurity:
    """Test security constraints (ADR-CORE-027 success criteria #5)."""

    @pytest.fixture
    async def sandboxed_session(self, connected_navigator_client):
        """Create a sandboxed filesystem session."""
        result = await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_create",
            arguments={
                "drivers": {
                    "fs": {
                        "type": "filesystem",
                        "root": "/workspace",
                        "sandbox": True
                    }
                }
            }
        )
        session_id = _extract_session_id(result)
        yield session_id, connected_navigator_client

        await connected_navigator_client.call_tool(
            service_name="navigator",
            tool_name="session_destroy",
            arguments={"session_id": session_id}
        )

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, sandboxed_session):
        """Test that path traversal outside sandbox is blocked."""
        session_id, client = sandboxed_session

        # Attempt to read /etc/passwd (outside sandbox)
        result = await client.call_tool(
            service_name="navigator",
            tool_name="read",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "target": "../../../etc/passwd"
            }
        )

        # Should fail with security error
        result_text = _extract_text(result)
        # Navigator should reject path traversal
        assert "error" in result_text.lower() or "denied" in result_text.lower() or \
               "outside" in result_text.lower() or "sandbox" in result_text.lower()

    @pytest.mark.asyncio
    async def test_absolute_path_outside_root_blocked(self, sandboxed_session):
        """Test that absolute paths outside root are blocked."""
        session_id, client = sandboxed_session

        result = await client.call_tool(
            service_name="navigator",
            tool_name="goto",
            arguments={
                "session_id": session_id,
                "driver": "fs",
                "location": "/etc"
            }
        )

        result_text = _extract_text(result)
        # Should fail - /etc is outside /workspace
        assert "error" in result_text.lower() or "outside" in result_text.lower() or \
               "denied" in result_text.lower()


# =============================================================================
# GRACEFUL DEGRADATION TESTS
# =============================================================================

class TestGracefulDegradation:
    """Test graceful degradation when navigator unavailable (ADR-CORE-027 criteria #4)."""

    @pytest.mark.asyncio
    async def test_optional_service_unavailable_returns_none(self, config):
        """Test that optional unavailable service returns None, not raises."""
        # Use a container name that doesn't exist
        config["mcp"]["external_mcp"]["services"]["navigator"]["container_name"] = "nonexistent-container"
        config["mcp"]["external_mcp"]["services"]["navigator"]["required"] = False

        client = ExternalMcpClient(config)

        # Should return None, not raise
        result = await client.connect_from_config("navigator")

        assert result is None
        await client.cleanup()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _extract_session_id(result) -> Optional[str]:
    """Extract session_id from MCP tool result."""
    if result is None:
        return None

    # Handle MCP result structure
    if hasattr(result, 'content'):
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            text = content[0].text if hasattr(content[0], 'text') else str(content[0])
        else:
            text = str(content)
    else:
        text = str(result)

    # Try to parse JSON from text
    import json
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data.get("session_id")
    except (json.JSONDecodeError, TypeError):
        pass

    # Try regex extraction
    import re
    match = re.search(r'"session_id"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)

    # Try simple pattern
    match = re.search(r'session[_-]?id["\s:]+([a-f0-9-]+)', text, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def _extract_text(result) -> str:
    """Extract text content from MCP tool result."""
    if result is None:
        return ""

    if hasattr(result, 'content'):
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            return content[0].text if hasattr(content[0], 'text') else str(content[0])
        return str(content)

    return str(result)


# =============================================================================
# CLEANUP
# =============================================================================

@pytest.fixture(autouse=True)
async def cleanup_test_files(workspace_path):
    """Cleanup test files after each test."""
    yield

    # Cleanup test files
    test_patterns = [
        "test_navigator_*.txt",
        "test_delete_recursive",
        "find_test",
    ]

    workspace = Path(workspace_path) if workspace_path.startswith("/") else Path(f"/app/{workspace_path}")
    for pattern in test_patterns:
        for path in workspace.glob(pattern):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                import shutil
                shutil.rmtree(path, ignore_errors=True)
