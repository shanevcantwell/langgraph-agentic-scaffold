"""
Unit tests for ExternalMcpClient connect_from_config methods.

Tests the config-driven connection logic without requiring actual containers.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from app.src.mcp.external_client import ExternalMcpClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def base_config() -> Dict[str, Any]:
    """Base config with surf (browser) enabled."""
    return {
        "mcp": {
            "external_mcp": {
                "enabled": True,
                "tracing_enabled": True,
                "services": {
                    "surf": {
                        "enabled": True,
                        "required": False,
                        "container_name": "surf-mcp",
                        "timeout_ms": 30000
                    }
                }
            }
        }
    }


@pytest.fixture
def mock_stdio_client():
    """Mock the stdio_client context manager."""
    with patch('app.src.mcp.external_client.stdio_client') as mock:
        # Create async context manager mock
        async_cm = AsyncMock()
        mock.return_value.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock.return_value.__aexit__ = AsyncMock(return_value=None)
        yield mock


@pytest.fixture
def mock_client_session():
    """Mock the ClientSession."""
    with patch('app.src.mcp.external_client.ClientSession') as mock:
        session_instance = AsyncMock()
        session_instance.initialize = AsyncMock()
        session_instance.list_tools = AsyncMock(return_value=MagicMock(
            tools=[MagicMock(name="session_create"), MagicMock(name="goto")]
        ))
        session_instance.call_tool = AsyncMock()

        # Make it work as async context manager
        mock.return_value.__aenter__ = AsyncMock(return_value=session_instance)
        mock.return_value.__aexit__ = AsyncMock(return_value=None)

        yield mock, session_instance


# =============================================================================
# TEST: connect_from_config
# =============================================================================

class TestConnectFromConfigLogic:
    """Test connect_from_config logic without actual connections."""

    @pytest.mark.asyncio
    async def test_disabled_service_returns_none(self, base_config):
        """Test that disabled service returns None without attempting connection."""
        base_config["mcp"]["external_mcp"]["services"]["surf"]["enabled"] = False

        client = ExternalMcpClient(base_config)
        result = await client.connect_from_config("surf")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_nonexistent_service_returns_none(self, base_config):
        """Test that nonexistent service returns None."""
        client = ExternalMcpClient(base_config)
        result = await client.connect_from_config("nonexistent")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_missing_connection_config_returns_none_for_optional(self, base_config):
        """Test optional service with missing connection config returns None."""
        base_config["mcp"]["external_mcp"]["services"]["bad_service"] = {
            "enabled": True,
            "required": False,
            # No container_name or command
        }

        client = ExternalMcpClient(base_config)
        result = await client.connect_from_config("bad_service")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_missing_connection_config_raises_for_required(self, base_config):
        """Test required service with missing connection config raises ValueError."""
        base_config["mcp"]["external_mcp"]["services"]["bad_required"] = {
            "enabled": True,
            "required": True,
            # No container_name or command
        }

        client = ExternalMcpClient(base_config)

        with pytest.raises(ValueError, match="no connection config"):
            await client.connect_from_config("bad_required")

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_container_name_builds_docker_exec_command(self, base_config):
        """Test that container_name mode builds correct docker exec command."""
        client = ExternalMcpClient(base_config)

        # Mock connect_service to capture the command
        captured_args = {}

        async def capture_connect(service_name, command, args, env=None):
            captured_args["command"] = command
            captured_args["args"] = args
            return ["tool1", "tool2"]

        client.connect_service = capture_connect

        await client.connect_from_config("surf")

        # Should use docker exec with container name
        assert captured_args["command"] == "docker"
        assert captured_args["args"] == ["exec", "-i", "surf-mcp", "surf-mcp"]

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_container_name_with_custom_entrypoint(self, base_config):
        """Test that custom entrypoint overrides default."""
        base_config["mcp"]["external_mcp"]["services"]["surf"]["entrypoint"] = "custom-cmd"

        client = ExternalMcpClient(base_config)

        captured_args = {}

        async def capture_connect(service_name, command, args, env=None):
            captured_args["args"] = args
            return ["tool1"]

        client.connect_service = capture_connect

        await client.connect_from_config("surf")

        # Should use custom entrypoint
        assert captured_args["args"] == ["exec", "-i", "surf-mcp", "custom-cmd"]

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_command_mode_uses_direct_command(self, base_config):
        """Test that command/args mode uses direct subprocess."""
        base_config["mcp"]["external_mcp"]["services"]["npm_service"] = {
            "enabled": True,
            "required": False,
            "command": "npx",
            "args": ["-y", "@some/mcp-server"]
        }

        client = ExternalMcpClient(base_config)

        captured_args = {}

        async def capture_connect(service_name, command, args, env=None):
            captured_args["command"] = command
            captured_args["args"] = args
            return ["tool1"]

        client.connect_service = capture_connect

        await client.connect_from_config("npm_service")

        # Should use direct command
        assert captured_args["command"] == "npx"
        assert captured_args["args"] == ["-y", "@some/mcp-server"]

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connection_failure_returns_none_for_optional(self, base_config):
        """Test that connection failure returns None for optional service."""
        client = ExternalMcpClient(base_config)

        async def fail_connect(*args, **kwargs):
            raise RuntimeError("Connection failed")

        client.connect_service = fail_connect

        # Should not raise, just return None
        result = await client.connect_from_config("surf")

        assert result is None
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connection_failure_raises_for_required(self, base_config):
        """Test that connection failure raises for required service."""
        base_config["mcp"]["external_mcp"]["services"]["surf"]["required"] = True

        client = ExternalMcpClient(base_config)

        async def fail_connect(*args, **kwargs):
            raise RuntimeError("Connection failed")

        client.connect_service = fail_connect

        with pytest.raises(RuntimeError, match="failed to connect"):
            await client.connect_from_config("surf")

        await client.cleanup()


# =============================================================================
# TEST: connect_all_from_config
# =============================================================================

class TestConnectAllFromConfig:
    """Test connect_all_from_config behavior."""

    @pytest.mark.asyncio
    async def test_globally_disabled_returns_empty_dict(self, base_config):
        """Test that globally disabled external MCP returns empty dict."""
        base_config["mcp"]["external_mcp"]["enabled"] = False

        client = ExternalMcpClient(base_config)
        result = await client.connect_all_from_config()

        assert result == {}
        await client.cleanup()

    @pytest.mark.asyncio
    async def test_connects_all_enabled_services(self, base_config):
        """Test that all enabled services are connected."""
        base_config["mcp"]["external_mcp"]["services"]["service2"] = {
            "enabled": True,
            "required": False,
            "command": "cmd2",
            "args": ["arg2"]
        }

        client = ExternalMcpClient(base_config)

        connected_services = []

        async def track_connect(service_name, command, args, env=None):
            connected_services.append(service_name)
            return [f"{service_name}_tool"]

        client.connect_service = track_connect

        result = await client.connect_all_from_config()

        assert "surf" in connected_services
        assert "service2" in connected_services
        assert result["surf"] == ["surf_tool"]
        assert result["service2"] == ["service2_tool"]

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_skips_disabled_services(self, base_config):
        """Test that disabled services are skipped."""
        base_config["mcp"]["external_mcp"]["services"]["disabled_service"] = {
            "enabled": False,
            "command": "should_not_run"
        }

        client = ExternalMcpClient(base_config)

        connected_services = []

        async def track_connect(service_name, command, args, env=None):
            connected_services.append(service_name)
            return ["tool"]

        client.connect_service = track_connect

        await client.connect_all_from_config()

        assert "disabled_service" not in connected_services

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_optional_failure_doesnt_stop_other_services(self, base_config):
        """Test that optional service failure doesn't stop other services."""
        base_config["mcp"]["external_mcp"]["services"]["service2"] = {
            "enabled": True,
            "required": False,
            "command": "cmd2",
            "args": []
        }

        client = ExternalMcpClient(base_config)

        call_count = [0]

        async def selective_fail(service_name, command, args, env=None):
            call_count[0] += 1
            if service_name == "surf":
                raise RuntimeError("Navigator failed")
            return ["tool"]

        client.connect_service = selective_fail

        result = await client.connect_all_from_config()

        # Should still have service2
        assert "service2" in result
        assert "surf" not in result
        assert call_count[0] == 2  # Both were attempted

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_required_failure_raises_immediately(self, base_config):
        """Test that required service failure raises RuntimeError."""
        base_config["mcp"]["external_mcp"]["services"]["surf"]["required"] = True
        base_config["mcp"]["external_mcp"]["services"]["service2"] = {
            "enabled": True,
            "required": False,
            "command": "cmd2",
            "args": []
        }

        client = ExternalMcpClient(base_config)

        async def fail_surf(service_name, command, args, env=None):
            if service_name == "surf":
                raise RuntimeError("Navigator failed")
            return ["tool"]

        client.connect_service = fail_surf

        with pytest.raises(RuntimeError, match="failed to connect"):
            await client.connect_all_from_config()

        await client.cleanup()


# =============================================================================
# TEST: Service Configuration Patterns
# =============================================================================

class TestServiceConfigPatterns:
    """Test various service configuration patterns."""

    @pytest.mark.asyncio
    async def test_container_name_mode_pattern(self, base_config):
        """Test the container_name mode pattern (ADR-CORE-027)."""
        # This is the pattern for surf
        service_config = base_config["mcp"]["external_mcp"]["services"]["surf"]

        assert service_config["enabled"] is True
        assert service_config["required"] is False
        assert service_config["container_name"] == "surf-mcp"
        assert "command" not in service_config  # Uses container_name, not command

    @pytest.mark.asyncio
    async def test_command_args_mode_pattern(self, base_config):
        """Test the command/args mode pattern."""
        base_config["mcp"]["external_mcp"]["services"]["npm_server"] = {
            "enabled": True,
            "required": False,
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/projects"]
        }

        client = ExternalMcpClient(base_config)
        service_config = client.config["services"]["npm_server"]

        assert service_config["command"] == "npx"
        assert "-y" in service_config["args"]
        assert "container_name" not in service_config

        await client.cleanup()

    @pytest.mark.asyncio
    async def test_docker_run_pattern(self, base_config):
        """Test the docker run pattern (legacy)."""
        base_config["mcp"]["external_mcp"]["services"]["docker_run_service"] = {
            "enabled": True,
            "required": False,
            "command": "docker",
            "args": ["run", "-i", "--rm", "-v", "/workspace:/projects", "mcp/filesystem", "/projects"]
        }

        client = ExternalMcpClient(base_config)

        captured_args = {}

        async def capture_connect(service_name, command, args, env=None):
            captured_args["command"] = command
            captured_args["args"] = args
            return ["tool"]

        client.connect_service = capture_connect

        await client.connect_from_config("docker_run_service")

        assert captured_args["command"] == "docker"
        assert "run" in captured_args["args"]
        assert "-i" in captured_args["args"]

        await client.cleanup()
