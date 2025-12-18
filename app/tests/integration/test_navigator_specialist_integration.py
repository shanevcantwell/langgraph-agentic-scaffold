"""
Integration tests for NavigatorSpecialist.

Tests the specialist with actual navigator container.

Prerequisites:
1. Start navigator container: docker-compose --profile navigator up -d
2. Run tests inside Docker: docker compose exec app pytest app/tests/integration/test_navigator_specialist_integration.py -v

Note on async/sync limitations:
NavigatorSpecialist uses sync_call_external_mcp internally which creates its own event loop.
The ExternalMcpClient sessions are bound to the event loop that created them.
This means we cannot mix async tests with NavigatorSpecialist's sync methods.

For comprehensive navigator testing, see test_navigator_mcp.py which tests the
ExternalMcpClient directly with async methods. The unit tests (test_navigator_specialist.py)
verify the NavigatorSpecialist logic with mocked clients.
"""
import pytest
import asyncio
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.navigator_specialist import NavigatorSpecialist
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
def specialist_config() -> Dict[str, Any]:
    """NavigatorSpecialist config."""
    return {
        "type": "hybrid",
        "prompt_file": "navigator_specialist_prompt.md",
        "description": "Test navigator specialist"
    }


@pytest.fixture
async def external_mcp_client(config):
    """Create and connect ExternalMcpClient (async fixture)."""
    client = ExternalMcpClient(config)
    tools = await client.connect_from_config("navigator")

    if tools is None:
        pytest.skip(
            "Navigator not available. Start with: docker-compose --profile navigator up -d"
        )

    yield client
    await client.cleanup()


@pytest.fixture
def connected_specialist(specialist_config, external_mcp_client):
    """NavigatorSpecialist with connected ExternalMcpClient."""
    specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
    specialist.external_mcp_client = external_mcp_client
    return specialist


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def create_state(user_message: str) -> Dict[str, Any]:
    """Create a minimal graph state with user message."""
    return {
        "messages": [HumanMessage(content=user_message)],
        "artifacts": {}
    }


def extract_response_text(result: Dict[str, Any]) -> str:
    """Extract response text from specialist result."""
    messages = result.get("messages", [])
    if messages and isinstance(messages[0], AIMessage):
        return messages[0].content
    return ""


# =============================================================================
# TEST: Pre-flight Checks
# =============================================================================

class TestNavigatorPreflightIntegration:
    """Test pre-flight checks with real navigator."""

    @pytest.mark.asyncio
    async def test_preflight_succeeds_with_navigator(self, connected_specialist):
        """Test that pre-flight check passes with connected navigator."""
        assert connected_specialist._perform_pre_flight_checks() is True

    @pytest.mark.asyncio
    async def test_preflight_fails_without_navigator(self, specialist_config):
        """Test that pre-flight check fails without navigator."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        # Don't attach client
        assert specialist._perform_pre_flight_checks() is False


# =============================================================================
# TEST: MCP Availability Check
# =============================================================================

class TestMcpAvailabilityIntegration:
    """Test MCP availability detection with real navigator."""

    @pytest.mark.asyncio
    async def test_mcp_is_available_when_connected(self, connected_specialist):
        """Test is_available returns True when navigator connected."""
        assert connected_specialist._mcp_is_available() is True

    @pytest.mark.asyncio
    async def test_mcp_is_available_when_not_connected(self, specialist_config):
        """Test is_available returns False when not connected."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        assert specialist._mcp_is_available() is False


# =============================================================================
# TEST: Graceful Degradation (ADR-CORE-027 Success Criteria #4)
# =============================================================================

class TestGracefulDegradationIntegration:
    """Test graceful degradation when navigator unavailable."""

    def test_graceful_message_when_unavailable(self, specialist_config):
        """Test that specialist provides helpful message when navigator unavailable."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        # Don't attach client - simulates navigator being down

        state = create_state("Delete the temp folder")
        result = specialist._execute_logic(state)

        response = extract_response_text(result)

        # Should provide helpful message about unavailability
        assert "navigator" in response.lower() or "unavailable" in response.lower()
        # Should mention alternatives
        assert "file" in response.lower()


# =============================================================================
# TEST: Path/Pattern Extraction (Integration-level verification)
# =============================================================================

class TestPathExtractionIntegration:
    """Verify path extraction works correctly (integration sanity check)."""

    def test_extract_quoted_path(self, specialist_config):
        """Test extracting path from quoted string."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        request = 'Delete the "my-folder" directory'
        path = specialist._extract_path_from_request(request)
        assert path == "my-folder"

    def test_extract_pattern_glob(self, specialist_config):
        """Test extracting glob pattern."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        request = "Find files matching *.py"
        pattern = specialist._extract_pattern_from_request(request)
        assert pattern == "*.py"

    def test_extract_pattern_extension(self, specialist_config):
        """Test extracting pattern from '.X files' phrase."""
        specialist = NavigatorSpecialist("navigator_specialist", specialist_config)
        request = "Find all .py files"
        pattern = specialist._extract_pattern_from_request(request)
        assert pattern == "**/*.py"


# =============================================================================
# NOTE: Direct Navigator Operations
#
# Direct navigator filesystem operations (session lifecycle, list, write, delete,
# find) are tested in test_navigator_mcp.py which tests ExternalMcpClient directly.
# This file focuses on NavigatorSpecialist behavior with and without navigator.
#
# Test coverage summary:
# - NavigatorSpecialist logic: app/tests/unit/test_navigator_specialist.py (33 tests)
# - Navigator MCP transport: app/tests/integration/test_navigator_mcp.py (23 tests)
# - NavigatorSpecialist integration: This file (8 tests)
# =============================================================================
