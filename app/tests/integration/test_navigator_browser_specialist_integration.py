"""
Integration tests for NavigatorBrowserSpecialist.

Tests the specialist with actual navigator container.

Prerequisites:
1. Start navigator container: docker-compose --profile navigator up -d
2. Run tests inside Docker: docker compose exec app pytest app/tests/integration/test_navigator_browser_specialist_integration.py -v

Note on async/sync limitations:
NavigatorBrowserSpecialist uses sync_call_external_mcp internally which creates its own event loop.
The ExternalMcpClient sessions are bound to the event loop that created them.

For comprehensive browser testing, see test_navigator_mcp.py which tests the
ExternalMcpClient directly with async methods. The unit tests (test_navigator_browser_specialist.py)
verify the NavigatorBrowserSpecialist logic with mocked clients.
"""
import pytest
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.navigator_browser_specialist import NavigatorBrowserSpecialist
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
    """NavigatorBrowserSpecialist config."""
    return {
        "type": "hybrid",
        "prompt_file": "navigator_browser_specialist_prompt.md",
        "description": "Test navigator browser specialist"
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
    """NavigatorBrowserSpecialist with connected ExternalMcpClient."""
    specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
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

class TestNavigatorBrowserPreflightIntegration:
    """Test pre-flight checks with real navigator."""

    @pytest.mark.asyncio
    async def test_preflight_succeeds_with_navigator(self, connected_specialist):
        """Test that pre-flight check passes with connected navigator."""
        assert connected_specialist._perform_pre_flight_checks() is True

    @pytest.mark.asyncio
    async def test_preflight_fails_without_navigator(self, specialist_config):
        """Test that pre-flight check fails without navigator."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        # Don't attach client
        assert specialist._perform_pre_flight_checks() is False


# =============================================================================
# TEST: MCP Availability Check
# =============================================================================

class TestMcpBrowserAvailabilityIntegration:
    """Test MCP availability detection with real navigator."""

    @pytest.mark.asyncio
    async def test_mcp_is_available_when_connected(self, connected_specialist):
        """Test is_available returns True when navigator connected."""
        assert connected_specialist._mcp_is_available() is True

    @pytest.mark.asyncio
    async def test_mcp_is_available_when_not_connected(self, specialist_config):
        """Test is_available returns False when not connected."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._mcp_is_available() is False


# =============================================================================
# TEST: Graceful Degradation (ADR-CORE-027 Success Criteria #4)
# =============================================================================

class TestBrowserGracefulDegradationIntegration:
    """Test graceful degradation when browser unavailable."""

    def test_graceful_message_when_unavailable(self, specialist_config):
        """Test that specialist provides helpful message when navigator unavailable."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        # Don't attach client - simulates navigator being down

        state = create_state("go to https://example.com")
        result = specialist._execute_logic(state)

        response = extract_response_text(result)

        # Should provide helpful message about unavailability
        assert "unavailable" in response.lower()
        # Should mention enabling browser navigation
        assert "browser" in response.lower() or "navigator" in response.lower()


# =============================================================================
# TEST: Operation Detection (Integration-level verification)
# =============================================================================

class TestOperationDetectionIntegration:
    """Verify operation detection works correctly (integration sanity check)."""

    def test_detect_navigate_operation(self, specialist_config):
        """Test detecting navigate operation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._detect_operation("go to https://example.com") == "navigate"
        assert specialist._detect_operation("navigate to https://google.com") == "navigate"

    def test_detect_click_operation(self, specialist_config):
        """Test detecting click operation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._detect_operation("click the submit button") == "click"
        assert specialist._detect_operation("press the login button") == "click"

    def test_detect_type_operation(self, specialist_config):
        """Test detecting type operation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._detect_operation("type 'hello' in the search box") == "type"

    def test_detect_read_operation(self, specialist_config):
        """Test detecting read operation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._detect_operation("read the page content") == "read"

    def test_detect_snapshot_operation(self, specialist_config):
        """Test detecting snapshot operation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._detect_operation("take a screenshot") == "snapshot"


# =============================================================================
# TEST: URL Extraction (Integration-level verification)
# =============================================================================

class TestUrlExtractionIntegration:
    """Verify URL extraction works correctly (integration sanity check)."""

    def test_extract_url_from_request(self, specialist_config):
        """Test extracting URL from request."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._extract_url("go to https://example.com") == "https://example.com"
        assert specialist._extract_url("visit http://test.com/page") == "http://test.com/page"

    def test_extract_url_strips_punctuation(self, specialist_config):
        """Test that URL extraction strips trailing punctuation."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist._extract_url("check out https://example.com.") == "https://example.com"


# =============================================================================
# TEST: Session Persistence (ADR-CORE-027 Phase 4)
# =============================================================================

class TestSessionPersistenceIntegration:
    """Test session persistence behavior (integration sanity checks)."""

    def test_get_existing_session_from_artifacts(self, specialist_config):
        """Test extracting session ID from artifacts."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "test-session-123",
                    "persist": True
                }
            }
        }
        session_id = specialist._get_existing_session(state)
        assert session_id == "test-session-123"

    def test_get_existing_session_returns_none_for_empty(self, specialist_config):
        """Test that None is returned for empty state."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        state = {"artifacts": {}}
        session_id = specialist._get_existing_session(state)
        assert session_id is None

    def test_cleanup_session_clears_artifact(self, specialist_config):
        """Test that cleanup clears the session artifact."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "session-to-clear",
                    "persist": True
                }
            }
        }
        # No client attached, so _destroy_session will fail silently
        result = specialist.cleanup_session(state)

        # Artifact should be cleared
        assert result["artifacts"]["browser_session"] is None
        assert "session ended" in result["messages"][0].content.lower()

    def test_session_artifact_key_constant(self, specialist_config):
        """Test that session artifact key is consistent."""
        specialist = NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)
        assert specialist.BROWSER_SESSION_ARTIFACT_KEY == "browser_session"


# =============================================================================
# NOTE: Direct Browser Operations
#
# Direct browser operations (goto, click, type, read, snapshot) are tested in
# test_navigator_mcp.py which tests ExternalMcpClient directly. This file
# focuses on NavigatorBrowserSpecialist behavior with and without navigator.
#
# Test coverage summary:
# - NavigatorBrowserSpecialist logic: app/tests/unit/test_navigator_browser_specialist.py (62 tests)
# - Navigator MCP browser transport: app/tests/integration/test_navigator_mcp.py (browser tests)
# - NavigatorBrowserSpecialist integration: This file (16 tests)
# =============================================================================
