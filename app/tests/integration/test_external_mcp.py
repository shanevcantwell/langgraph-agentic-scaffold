"""
Integration tests for External MCP Container Integration (ADR-MCP-003).

Tests external MCP filesystem server connectivity, operations, error handling,
and integration with the specialist system.

NOTE: These tests are SKIPPED because mcp/filesystem container has been removed.
Using internal FileSpecialist MCP instead. Keep tests for future external MCP services.

Prerequisites:
1. mcp/filesystem Docker image must be built/pulled
2. config.yaml must have external_mcp.enabled: true
3. WORKSPACE_PATH environment variable must be set

Run with: pytest app/tests/integration/test_external_mcp.py -v
"""
import pytest

# Skip entire module - mcp/filesystem container removed, using internal FileSpecialist
pytestmark = pytest.mark.skip(reason="mcp/filesystem container removed - using internal FileSpecialist MCP")

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Dict, Any

from app.src.mcp.external_client import ExternalMcpClient, sync_call_external_mcp
from app.src.utils.config_loader import ConfigLoader


@pytest.fixture
def config():
    """Load configuration from config.yaml."""
    config_loader = ConfigLoader()
    return config_loader.get_config()


@pytest.fixture
def workspace_path():
    """Get workspace path from environment or use default."""
    return os.getenv("WORKSPACE_PATH", "workspace")


@pytest.fixture
async def external_mcp_client(config):
    """
    Create and initialize ExternalMcpClient.

    Yields client instance, then cleans up on teardown.
    """
    client = ExternalMcpClient(config)
    yield client
    await client.cleanup()


@pytest.fixture
async def connected_filesystem_client(external_mcp_client, workspace_path):
    """
    ExternalMcpClient with filesystem service already connected.

    This fixture handles connection setup and teardown.
    """
    # Connect to filesystem service
    tools = await external_mcp_client.connect_service(
        service_name="filesystem",
        command="docker",
        args=[
            "run",
            "-i",
            "--rm",
            "-v",
            f"{workspace_path}:/projects",
            "mcp/filesystem",
            "/projects"
        ]
    )

    assert len(tools) > 0, "Filesystem service should provide tools"
    assert "read_file" in tools
    assert "write_file" in tools
    assert "list_directory" in tools

    yield external_mcp_client


class TestExternalMcpConnection:
    """Test external MCP container connection lifecycle."""

    @pytest.mark.asyncio
    async def test_client_initialization(self, config):
        """Test that ExternalMcpClient initializes with valid config."""
        client = ExternalMcpClient(config)

        assert client is not None
        assert client.sessions == {}
        assert client.config == config.get("mcp", {}).get("external_mcp", {})

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connect_filesystem_service(self, external_mcp_client, workspace_path):
        """Test connecting to filesystem MCP service."""
        tools = await external_mcp_client.connect_service(
            service_name="filesystem",
            command="docker",
            args=[
                "run",
                "-i",
                "--rm",
                "-v",
                f"{workspace_path}:/projects",
                "mcp/filesystem",
                "/projects"
            ]
        )

        # Verify connection success
        assert external_mcp_client.is_connected("filesystem")
        assert "filesystem" in external_mcp_client.get_connected_services()

        # Verify tools available
        assert len(tools) > 0
        expected_tools = ["read_file", "write_file", "list_directory"]
        for tool in expected_tools:
            assert tool in tools, f"Expected tool '{tool}' not found"

    @pytest.mark.asyncio
    async def test_duplicate_connection_raises_error(self, connected_filesystem_client, workspace_path):
        """Test that connecting to same service twice raises ValueError."""
        with pytest.raises(ValueError, match="already connected"):
            await connected_filesystem_client.connect_service(
                service_name="filesystem",
                command="docker",
                args=[
                    "run", "-i", "--rm", "-v",
                    f"{workspace_path}:/projects",
                    "mcp/filesystem", "/projects"
                ]
            )

    @pytest.mark.asyncio
    async def test_health_check(self, connected_filesystem_client):
        """Test health check on connected service."""
        is_healthy = await connected_filesystem_client.health_check("filesystem")
        assert is_healthy is True

    @pytest.mark.asyncio
    async def test_list_tools(self, connected_filesystem_client):
        """Test listing tools for connected service."""
        tools = await connected_filesystem_client.list_tools("filesystem")

        assert isinstance(tools, list)
        assert len(tools) > 0
        assert "read_file" in tools


class TestExternalMcpFileOperations:
    """Test filesystem operations via external MCP."""

    @pytest.mark.asyncio
    async def test_list_directory(self, connected_filesystem_client):
        """Test listing directory contents."""
        result = await connected_filesystem_client.call_tool(
            service_name="filesystem",
            tool_name="list_directory",
            arguments={"path": "/projects"}
        )

        assert result is not None
        # MCP result structure may vary - basic validation
        assert hasattr(result, 'content') or isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_write_and_read_file(self, connected_filesystem_client):
        """Test writing and reading a file via external MCP."""
        test_content = "External MCP test content\nLine 2\nLine 3"
        test_path = "/projects/test_external_mcp.txt"

        # Write file
        write_result = await connected_filesystem_client.call_tool(
            service_name="filesystem",
            tool_name="write_file",
            arguments={
                "path": test_path,
                "content": test_content
            }
        )

        assert write_result is not None

        # Read file back
        read_result = await connected_filesystem_client.call_tool(
            service_name="filesystem",
            tool_name="read_file",
            arguments={"path": test_path}
        )

        assert read_result is not None
        # Validate content matches
        # Note: MCP response structure may wrap content
        if hasattr(read_result, 'content'):
            content = read_result.content
            # Content might be wrapped in list of TextContent objects
            if isinstance(content, list) and len(content) > 0:
                actual_content = content[0].text if hasattr(content[0], 'text') else str(content[0])
            else:
                actual_content = str(content)
        else:
            actual_content = str(read_result)

        assert test_content in actual_content


class TestExternalMcpErrorHandling:
    """Test fail-fast error handling (ADR-MCP-003 Stage 1)."""

    @pytest.mark.asyncio
    async def test_call_tool_on_disconnected_service(self, external_mcp_client):
        """Test that calling tool on disconnected service raises ValueError."""
        with pytest.raises(ValueError, match="not connected"):
            await external_mcp_client.call_tool(
                service_name="nonexistent",
                tool_name="read_file",
                arguments={"path": "/test.txt"}
            )

    @pytest.mark.asyncio
    async def test_invalid_tool_name(self, connected_filesystem_client):
        """Test that invalid tool name raises RuntimeError."""
        with pytest.raises(RuntimeError, match="tool call failed"):
            await connected_filesystem_client.call_tool(
                service_name="filesystem",
                tool_name="nonexistent_tool",
                arguments={}
            )

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, connected_filesystem_client):
        """Test that reading nonexistent file raises RuntimeError."""
        with pytest.raises(RuntimeError):
            await connected_filesystem_client.call_tool(
                service_name="filesystem",
                tool_name="read_file",
                arguments={"path": "/projects/nonexistent_file_12345.txt"}
            )

    @pytest.mark.asyncio
    async def test_invalid_path_outside_allowed_directory(self, connected_filesystem_client):
        """Test that accessing path outside allowed directory fails."""
        with pytest.raises(RuntimeError):
            await connected_filesystem_client.call_tool(
                service_name="filesystem",
                tool_name="read_file",
                arguments={"path": "/etc/passwd"}  # Outside /projects
            )


# Sync/Async Bridge tests removed - the sync bridge (sync_call_external_mcp)
# creates new event loops which conflicts with pytest-asyncio's event loop management.
# Per ADR-CORE-014, the sync bridge is a temporary workaround pending async migration.
# Direct async calls should be used in tests instead.


class TestSpecialistIntegration:
    """Test that specialists can use external MCP client."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Requires full application dependencies (google.generativeai, etc.)")
    async def test_specialist_external_mcp_attribute(self, config):
        """Test that specialists receive external_mcp_client attribute."""
        # This is a smoke test - real integration tested via GraphBuilder
        from app.src.workflow.graph_builder import GraphBuilder

        builder = GraphBuilder(config)
        builder.build()

        # Initialize external MCP
        if config.get("mcp", {}).get("external_mcp", {}).get("enabled", False):
            await builder.initialize_external_mcp()

            # Verify specialists have external_mcp_client attached
            for specialist_name, specialist_instance in builder.specialists.items():
                assert hasattr(specialist_instance, "external_mcp_client")

                # If external MCP enabled, client should not be None
                if builder.external_mcp_client is not None:
                    assert specialist_instance.external_mcp_client is not None

            # Cleanup
            await builder.cleanup_external_mcp()


# ==============================================================================
# CLEANUP FIXTURES
# ==============================================================================

@pytest.fixture(autouse=True)
async def cleanup_test_files(workspace_path):
    """
    Cleanup test files after each test.

    Runs after test completion to remove temporary files created during tests.
    """
    yield

    # Cleanup test files
    test_files = [
        Path(workspace_path) / "test_external_mcp.txt",
        Path(workspace_path) / "test_sync_bridge.txt",
    ]

    for test_file in test_files:
        if test_file.exists():
            test_file.unlink()
