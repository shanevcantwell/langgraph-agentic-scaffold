"""
Unit tests for NavigatorBrowserSpecialist.

Tests the specialist logic with mocked ExternalMcpClient.
"""
import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.navigator_browser_specialist import NavigatorBrowserSpecialist


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def specialist_config() -> Dict[str, Any]:
    """Basic specialist configuration."""
    return {
        "type": "hybrid",
        "prompt_file": "navigator_browser_specialist_prompt.md",
        "description": "Test navigator browser specialist"
    }


@pytest.fixture
def browser_specialist(specialist_config):
    """Create NavigatorBrowserSpecialist instance."""
    return NavigatorBrowserSpecialist("navigator_browser_specialist", specialist_config)


@pytest.fixture
def mock_external_client():
    """Create mock ExternalMcpClient."""
    client = MagicMock()
    client.is_connected.return_value = True
    return client


@pytest.fixture
def connected_specialist(browser_specialist, mock_external_client):
    """NavigatorBrowserSpecialist with mock client attached."""
    browser_specialist.external_mcp_client = mock_external_client
    return browser_specialist


# =============================================================================
# TEST: Initialization and Pre-flight Checks
# =============================================================================

class TestNavigatorBrowserSpecialistInit:
    """Test specialist initialization and pre-flight checks."""

    def test_init_sets_name_and_config(self, browser_specialist, specialist_config):
        """Test that init properly sets name and config."""
        assert browser_specialist.specialist_name == "navigator_browser_specialist"
        assert browser_specialist.specialist_config == specialist_config
        # external_mcp_client is injected after init, not set by base class
        assert not hasattr(browser_specialist, 'external_mcp_client') or browser_specialist.external_mcp_client is None

    def test_preflight_fails_without_client(self, browser_specialist):
        """Test pre-flight check fails when client not injected."""
        assert browser_specialist._perform_pre_flight_checks() is False

    def test_preflight_fails_when_not_connected(self, browser_specialist, mock_external_client):
        """Test pre-flight check fails when navigator not connected."""
        mock_external_client.is_connected.return_value = False
        browser_specialist.external_mcp_client = mock_external_client

        assert browser_specialist._perform_pre_flight_checks() is False
        mock_external_client.is_connected.assert_called_with("navigator")

    def test_preflight_succeeds_when_connected(self, connected_specialist, mock_external_client):
        """Test pre-flight check passes when navigator connected."""
        assert connected_specialist._perform_pre_flight_checks() is True
        mock_external_client.is_connected.assert_called_with("navigator")


# =============================================================================
# TEST: Session Management
# =============================================================================

class TestBrowserSessionManagement:
    """Test browser session create/destroy logic."""

    def test_create_browser_session_extracts_session_id(self, connected_specialist):
        """Test browser session creation extracts session_id."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"session_id": "browser-session-123"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result):
            session_id = connected_specialist._create_browser_session()

        assert session_id == "browser-session-123"

    def test_create_browser_session_passes_headless_option(self, connected_specialist):
        """Test browser session creation passes headless option."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"session_id": "browser-session-123"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            connected_specialist._create_browser_session(headless=False)

        call_args = mock_call.call_args[0]
        assert call_args[3]["drivers"]["web"]["headless"] is False

    def test_create_browser_session_returns_none_on_failure(self, connected_specialist):
        """Test browser session creation returns None on failure."""
        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', side_effect=Exception("Connection failed")):
            session_id = connected_specialist._create_browser_session()

        assert session_id is None

    def test_destroy_session_calls_navigator(self, connected_specialist):
        """Test session destruction calls navigator."""
        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp') as mock_call:
            connected_specialist._destroy_session("browser-session-123")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "session_destroy"
        assert call_args[3]["session_id"] == "browser-session-123"


# =============================================================================
# TEST: Operation Detection
# =============================================================================

class TestOperationDetection:
    """Test operation type detection from user requests."""

    def test_detect_navigate_with_url(self, browser_specialist):
        """Test detecting navigation request with URL."""
        assert browser_specialist._detect_operation("go to https://example.com") == "navigate"
        assert browser_specialist._detect_operation("navigate to https://google.com") == "navigate"
        assert browser_specialist._detect_operation("open https://test.com") == "navigate"
        assert browser_specialist._detect_operation("visit https://site.org") == "navigate"

    def test_detect_navigate_with_url_only(self, browser_specialist):
        """Test detecting navigation when URL is present."""
        assert browser_specialist._detect_operation("https://example.com") == "navigate"

    def test_detect_click_request(self, browser_specialist):
        """Test detecting click requests."""
        assert browser_specialist._detect_operation("click the submit button") == "click"
        assert browser_specialist._detect_operation("press the login button") == "click"
        assert browser_specialist._detect_operation("tap the link") == "click"

    def test_detect_type_request(self, browser_specialist):
        """Test detecting type requests."""
        assert browser_specialist._detect_operation("type 'hello' in the search box") == "type"
        assert browser_specialist._detect_operation("enter text into the input") == "type"
        assert browser_specialist._detect_operation("fill in the form") == "type"

    def test_detect_read_request(self, browser_specialist):
        """Test detecting read requests."""
        assert browser_specialist._detect_operation("read the page content") == "read"
        assert browser_specialist._detect_operation("get the article text") == "read"
        assert browser_specialist._detect_operation("extract the main content") == "read"

    def test_detect_snapshot_request(self, browser_specialist):
        """Test detecting screenshot requests."""
        assert browser_specialist._detect_operation("take a screenshot") == "snapshot"
        assert browser_specialist._detect_operation("capture the page") == "snapshot"
        assert browser_specialist._detect_operation("snapshot the screen") == "snapshot"

    def test_detect_unknown_request(self, browser_specialist):
        """Test detecting unknown requests."""
        assert browser_specialist._detect_operation("do something random") == "unknown"


# =============================================================================
# TEST: URL Extraction
# =============================================================================

class TestUrlExtraction:
    """Test URL extraction from user requests."""

    def test_extract_https_url(self, browser_specialist):
        """Test extracting HTTPS URL."""
        url = browser_specialist._extract_url("go to https://example.com")
        assert url == "https://example.com"

    def test_extract_http_url(self, browser_specialist):
        """Test extracting HTTP URL."""
        url = browser_specialist._extract_url("navigate to http://test.com")
        assert url == "http://test.com"

    def test_extract_url_with_path(self, browser_specialist):
        """Test extracting URL with path."""
        url = browser_specialist._extract_url("open https://example.com/page/subpage")
        assert url == "https://example.com/page/subpage"

    def test_extract_url_strips_punctuation(self, browser_specialist):
        """Test that trailing punctuation is stripped."""
        url = browser_specialist._extract_url("check out https://example.com.")
        assert url == "https://example.com"

    def test_extract_url_returns_none_when_missing(self, browser_specialist):
        """Test that None is returned when no URL present."""
        url = browser_specialist._extract_url("go to the website")
        assert url is None


# =============================================================================
# TEST: Element Description Extraction
# =============================================================================

class TestElementDescriptionExtraction:
    """Test element description extraction from user requests."""

    def test_extract_quoted_element(self, browser_specialist):
        """Test extracting quoted element description."""
        element = browser_specialist._extract_element_description('click the "Submit" button')
        assert element == "Submit"

    def test_extract_element_from_click_pattern(self, browser_specialist):
        """Test extracting element from click pattern."""
        element = browser_specialist._extract_element_description("click the blue button")
        assert element == "blue"

    def test_extract_element_returns_none_for_unclear(self, browser_specialist):
        """Test element extraction returns None for unclear requests."""
        element = browser_specialist._extract_element_description("do something")
        assert element is None


# =============================================================================
# TEST: Text to Type Extraction
# =============================================================================

class TestTextToTypeExtraction:
    """Test text extraction for type operations."""

    def test_extract_quoted_text(self, browser_specialist):
        """Test extracting quoted text."""
        text = browser_specialist._extract_text_to_type("type 'hello world' in the box")
        assert text == "hello world"

    def test_extract_double_quoted_text(self, browser_specialist):
        """Test extracting double-quoted text."""
        text = browser_specialist._extract_text_to_type('type "test query" into search')
        assert text == "test query"

    def test_extract_text_returns_none_for_unclear(self, browser_specialist):
        """Test text extraction returns None for unclear requests."""
        text = browser_specialist._extract_text_to_type("type something")
        assert text is None


# =============================================================================
# TEST: Browser Operations
# =============================================================================

class TestBrowserOperations:
    """Test the browser operation methods."""

    def test_navigate_to_calls_navigator(self, connected_specialist):
        """Test navigate_to calls navigator goto."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"url": "https://example.com"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            result = connected_specialist.navigate_to("session-123", "https://example.com")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "goto"
        assert call_args[3]["location"] == "https://example.com"
        assert call_args[3]["driver"] == "web"

    def test_click_element_calls_navigator(self, connected_specialist):
        """Test click_element calls navigator click."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"clicked": true}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            result = connected_specialist.click_element("session-123", "the submit button")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "click"
        assert call_args[3]["target"] == "the submit button"

    def test_type_text_calls_navigator(self, connected_specialist):
        """Test type_text calls navigator type."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"typed": true}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            result = connected_specialist.type_text("session-123", "hello", "search box")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "type"
        assert call_args[3]["text"] == "hello"
        assert call_args[3]["target"] == "search box"

    def test_read_content_calls_navigator(self, connected_specialist):
        """Test read_content calls navigator read."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"content": "Page text"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            result = connected_specialist.read_content("session-123")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "read"
        assert call_args[3]["driver"] == "web"

    def test_take_snapshot_calls_navigator(self, connected_specialist):
        """Test take_snapshot calls navigator snapshot."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"image": "base64..."}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result) as mock_call:
            result = connected_specialist.take_snapshot("session-123")

        mock_call.assert_called_once()
        call_args = mock_call.call_args[0]
        assert call_args[2] == "snapshot"


# =============================================================================
# TEST: Request Handlers
# =============================================================================

class TestRequestHandlers:
    """Test the request handler methods."""

    def test_handle_browser_unavailable(self, browser_specialist):
        """Test graceful message when browser unavailable."""
        state = {"messages": [HumanMessage(content="go to https://example.com")]}
        result = browser_specialist._handle_browser_unavailable(state)

        assert "messages" in result
        assert "unavailable" in result["messages"][0].content.lower()

    def test_handle_navigate_success(self, connected_specialist):
        """Test successful navigation."""
        mock_result = {"url": "https://example.com"}

        with patch.object(connected_specialist, 'navigate_to', return_value=mock_result):
            result = connected_specialist._handle_navigate_request(
                "session-123",
                "go to https://example.com"
            )

        assert "Navigated to" in result["messages"][0].content
        assert "browser_operation" in result.get("artifacts", {})

    def test_handle_navigate_no_url(self, connected_specialist):
        """Test navigation without URL."""
        result = connected_specialist._handle_navigate_request("session-123", "go to the website")

        assert "couldn't find a URL" in result["messages"][0].content

    def test_handle_click_success(self, connected_specialist):
        """Test successful click."""
        mock_result = {"clicked": True}

        with patch.object(connected_specialist, 'click_element', return_value=mock_result):
            result = connected_specialist._handle_click_request(
                "session-123",
                'click the "Submit" button'
            )

        assert "Clicked" in result["messages"][0].content

    def test_handle_click_error(self, connected_specialist):
        """Test click with error."""
        mock_result = {"error": "Element not found"}

        with patch.object(connected_specialist, 'click_element', return_value=mock_result):
            result = connected_specialist._handle_click_request(
                "session-123",
                'click the "Submit" button'
            )

        assert "Failed to click" in result["messages"][0].content

    def test_handle_type_success(self, connected_specialist):
        """Test successful type."""
        mock_result = {"typed": True}

        with patch.object(connected_specialist, 'type_text', return_value=mock_result):
            result = connected_specialist._handle_type_request(
                "session-123",
                "type 'hello' in the search box"
            )

        assert "Typed" in result["messages"][0].content

    def test_handle_read_success(self, connected_specialist):
        """Test successful read."""
        mock_result = {"content": "Page content here"}

        with patch.object(connected_specialist, 'read_content', return_value=mock_result):
            result = connected_specialist._handle_read_request("session-123", "read the page")

        assert "Page content" in result["messages"][0].content

    def test_handle_snapshot_success(self, connected_specialist):
        """Test successful snapshot."""
        mock_result = {"image": "base64data"}

        with patch.object(connected_specialist, 'take_snapshot', return_value=mock_result):
            result = connected_specialist._handle_snapshot_request("session-123", "take screenshot")

        assert "Screenshot captured" in result["messages"][0].content


# =============================================================================
# TEST: Execute Logic
# =============================================================================

class TestExecuteLogic:
    """Test the main execution logic."""

    def test_execute_without_client(self, browser_specialist):
        """Test execution without client returns unavailable message."""
        state = {"messages": [HumanMessage(content="go to https://example.com")]}
        result = browser_specialist._execute_logic(state)

        assert "unavailable" in result["messages"][0].content.lower()

    def test_execute_creates_session_and_persists_by_default(self, connected_specialist):
        """Test execution creates session and persists it by default (Phase 4)."""
        state = {"messages": [HumanMessage(content="go to https://example.com")]}

        mock_session_result = MagicMock()
        mock_session_result.content = [MagicMock(text='{"session_id": "test-session"}')]

        mock_nav_result = {"url": "https://example.com"}

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_session_result) as mock_call:
            with patch.object(connected_specialist, 'navigate_to', return_value=mock_nav_result):
                with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
                    result = connected_specialist._execute_logic(state)

        # Session is NOT destroyed by default (persist_session=True)
        mock_destroy.assert_not_called()
        # Session info should be in artifacts for reuse
        assert "browser_session" in result["artifacts"]


# =============================================================================
# TEST: MCP Registration
# =============================================================================

class TestMcpRegistration:
    """Test MCP service registration."""

    def test_register_mcp_services(self, connected_specialist):
        """Test that MCP services are registered correctly."""
        mock_registry = MagicMock()

        connected_specialist.register_mcp_services(mock_registry)

        mock_registry.register_service.assert_called_once()
        call_args = mock_registry.register_service.call_args
        assert call_args[0][0] == "navigator_browser_specialist"

        services = call_args[0][1]
        assert "navigate_to" in services
        assert "click_element" in services
        assert "type_text" in services
        assert "read_content" in services
        assert "take_snapshot" in services
        assert "is_available" in services

    def test_mcp_is_available(self, connected_specialist):
        """Test is_available MCP service."""
        assert connected_specialist._mcp_is_available() is True

    def test_mcp_is_available_when_not_connected(self, browser_specialist):
        """Test is_available returns False when not connected."""
        assert browser_specialist._mcp_is_available() is False


# =============================================================================
# TEST: Result Parsing
# =============================================================================

class TestResultParsing:
    """Test result parsing from navigator responses."""

    def test_parse_json_result(self, browser_specialist):
        """Test parsing JSON result."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"key": "value"}')]

        parsed = browser_specialist._parse_result(mock_result)

        assert parsed == {"key": "value"}

    def test_parse_non_json_result(self, browser_specialist):
        """Test parsing non-JSON result falls back to string conversion."""
        mock_result = MagicMock()
        # When json.loads fails on non-JSON text, _parse_result returns str(result)
        # which is the full MagicMock representation, not just the text content
        mock_content_item = MagicMock()
        mock_content_item.text = 'Plain text response'
        mock_result.content = [mock_content_item]

        parsed = browser_specialist._parse_result(mock_result)

        # Since "Plain text response" is not valid JSON, it falls through to
        # the except clause and returns {"content": str(result)}
        assert "content" in parsed

    def test_parse_none_result(self, browser_specialist):
        """Test parsing None result."""
        parsed = browser_specialist._parse_result(None)

        assert "error" in parsed


# =============================================================================
# TEST: Session Persistence (ADR-CORE-027 Phase 4)
# =============================================================================

class TestSessionPersistence:
    """Test session persistence across invocations."""

    def test_get_existing_session_from_artifacts(self, browser_specialist):
        """Test extracting existing session from state artifacts."""
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "existing-session-123",
                    "persist": True
                }
            }
        }
        session_id = browser_specialist._get_existing_session(state)
        assert session_id == "existing-session-123"

    def test_get_existing_session_returns_none_when_missing(self, browser_specialist):
        """Test that None is returned when no session artifact exists."""
        state = {"artifacts": {}}
        session_id = browser_specialist._get_existing_session(state)
        assert session_id is None

    def test_get_existing_session_returns_none_for_empty_state(self, browser_specialist):
        """Test that None is returned for empty state."""
        state = {}
        session_id = browser_specialist._get_existing_session(state)
        assert session_id is None

    def test_validate_session_returns_true_for_valid_session(self, connected_specialist):
        """Test session validation succeeds for valid session."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"current": "/"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result):
            is_valid = connected_specialist._validate_session("valid-session-123")

        assert is_valid is True

    def test_validate_session_returns_false_for_error(self, connected_specialist):
        """Test session validation fails when navigator returns error."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"error": "Session not found"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_result):
            is_valid = connected_specialist._validate_session("invalid-session-123")

        assert is_valid is False

    def test_validate_session_returns_false_on_exception(self, connected_specialist):
        """Test session validation fails on exception."""
        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', side_effect=Exception("Connection error")):
            is_valid = connected_specialist._validate_session("session-123")

        assert is_valid is False

    def test_get_or_create_session_reuses_valid_session(self, connected_specialist):
        """Test that valid existing session is reused."""
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "existing-session-123",
                    "persist": True
                }
            }
        }

        with patch.object(connected_specialist, '_validate_session', return_value=True):
            session_id = connected_specialist._get_or_create_session(state, persist=True)

        assert session_id == "existing-session-123"

    def test_get_or_create_session_creates_new_when_invalid(self, connected_specialist):
        """Test that new session is created when existing is invalid."""
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "expired-session-123",
                    "persist": True
                }
            }
        }

        with patch.object(connected_specialist, '_validate_session', return_value=False):
            with patch.object(connected_specialist, '_create_browser_session', return_value="new-session-456"):
                session_id = connected_specialist._get_or_create_session(state, persist=True)

        assert session_id == "new-session-456"

    def test_get_or_create_session_creates_new_when_not_persisting(self, connected_specialist):
        """Test that new session is always created when persist=False."""
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "existing-session-123",
                    "persist": True
                }
            }
        }

        with patch.object(connected_specialist, '_create_browser_session', return_value="new-session-456"):
            session_id = connected_specialist._get_or_create_session(state, persist=False)

        assert session_id == "new-session-456"

    def test_merge_result_with_session_adds_artifact(self, browser_specialist):
        """Test that session info is merged into result artifacts."""
        result = {
            "messages": [AIMessage(content="Done")],
            "artifacts": {"browser_operation": {"type": "navigate"}}
        }

        merged = browser_specialist._merge_result_with_session(result, "session-123", persist=True)

        assert "browser_session" in merged["artifacts"]
        assert merged["artifacts"]["browser_session"]["session_id"] == "session-123"
        # Original artifact preserved
        assert "browser_operation" in merged["artifacts"]

    def test_merge_result_with_session_skips_when_not_persisting(self, browser_specialist):
        """Test that merge is skipped when persist=False."""
        result = {
            "messages": [AIMessage(content="Done")],
            "artifacts": {"browser_operation": {"type": "navigate"}}
        }

        merged = browser_specialist._merge_result_with_session(result, "session-123", persist=False)

        assert "browser_session" not in merged.get("artifacts", {})

    def test_cleanup_session_destroys_existing_session(self, connected_specialist):
        """Test that cleanup destroys the existing session."""
        state = {
            "artifacts": {
                "browser_session": {
                    "session_id": "session-to-cleanup-123",
                    "persist": True
                }
            }
        }

        with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
            result = connected_specialist.cleanup_session(state)

        mock_destroy.assert_called_once_with("session-to-cleanup-123")
        assert result["artifacts"]["browser_session"] is None
        assert "session ended" in result["messages"][0].content.lower()

    def test_cleanup_session_handles_no_existing_session(self, connected_specialist):
        """Test that cleanup handles missing session gracefully."""
        state = {"artifacts": {}}

        with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
            result = connected_specialist.cleanup_session(state)

        mock_destroy.assert_not_called()
        assert result["artifacts"]["browser_session"] is None

    def test_execute_logic_persists_session_by_default(self, connected_specialist):
        """Test that execute_logic persists session by default."""
        state = {"messages": [HumanMessage(content="go to https://example.com")]}

        mock_session_result = MagicMock()
        mock_session_result.content = [MagicMock(text='{"session_id": "new-session-123"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_session_result):
            with patch.object(connected_specialist, 'navigate_to', return_value={"url": "https://example.com"}):
                with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
                    result = connected_specialist._execute_logic(state)

        # Session should NOT be destroyed when persisting
        mock_destroy.assert_not_called()
        # Session should be in artifacts
        assert "browser_session" in result["artifacts"]
        assert result["artifacts"]["browser_session"]["session_id"] == "new-session-123"

    def test_execute_logic_destroys_session_when_not_persisting(self, connected_specialist):
        """Test that execute_logic destroys session when persist_session=False."""
        state = {"messages": [HumanMessage(content="go to https://example.com")]}

        mock_session_result = MagicMock()
        mock_session_result.content = [MagicMock(text='{"session_id": "temp-session-123"}')]

        with patch('app.src.specialists.navigator_browser_specialist.sync_call_external_mcp', return_value=mock_session_result):
            with patch.object(connected_specialist, 'navigate_to', return_value={"url": "https://example.com"}):
                with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
                    result = connected_specialist._execute_logic(state, persist_session=False)

        # Session should be destroyed when not persisting
        mock_destroy.assert_called_once_with("temp-session-123")
        # Session should NOT be in artifacts
        assert "browser_session" not in result.get("artifacts", {})
