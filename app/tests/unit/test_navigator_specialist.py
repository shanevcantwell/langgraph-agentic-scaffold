"""
Unit tests for NavigatorSpecialist.

Tests the specialist logic with mocked ExternalMcpClient.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.navigator_specialist import NavigatorSpecialist


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def specialist_config() -> Dict[str, Any]:
    """Basic specialist configuration."""
    return {
        "type": "hybrid",
        "prompt_file": "navigator_specialist_prompt.md",
        "description": "Test navigator specialist"
    }


@pytest.fixture
def navigator_specialist(specialist_config):
    """Create NavigatorSpecialist instance."""
    return NavigatorSpecialist("navigator_specialist", specialist_config)


@pytest.fixture
def mock_external_client():
    """Create mock ExternalMcpClient."""
    client = MagicMock()
    client.is_connected.return_value = True
    return client


@pytest.fixture
def connected_specialist(navigator_specialist, mock_external_client):
    """NavigatorSpecialist with mock client attached."""
    navigator_specialist.external_mcp_client = mock_external_client
    return navigator_specialist


# =============================================================================
# TEST: Initialization and Pre-flight Checks
# =============================================================================

class TestNavigatorSpecialistInit:
    """Test specialist initialization and pre-flight checks."""

    def test_init_sets_name_and_config(self, navigator_specialist, specialist_config):
        """Test that init properly sets name and config."""
        assert navigator_specialist.specialist_name == "navigator_specialist"
        assert navigator_specialist.specialist_config == specialist_config
        assert navigator_specialist.external_mcp_client is None

    def test_preflight_passes_without_client_for_loading(self, navigator_specialist):
        """Test pre-flight passes when client not injected (allows loading).

        external_mcp_client is injected AFTER specialist loading by GraphBuilder,
        so pre-flight must return True to allow the specialist to be loaded.
        Runtime checks handle unavailability gracefully.
        """
        assert navigator_specialist._perform_pre_flight_checks() is True

    def test_preflight_fails_when_not_connected(self, navigator_specialist, mock_external_client):
        """Test pre-flight check fails when navigator not connected."""
        mock_external_client.is_connected.return_value = False
        navigator_specialist.external_mcp_client = mock_external_client

        assert navigator_specialist._perform_pre_flight_checks() is False
        mock_external_client.is_connected.assert_called_with("navigator")

    def test_preflight_succeeds_when_connected(self, connected_specialist, mock_external_client):
        """Test pre-flight check passes when navigator connected."""
        assert connected_specialist._perform_pre_flight_checks() is True
        mock_external_client.is_connected.assert_called_with("navigator")


# =============================================================================
# TEST: Session Management
# =============================================================================

class TestSessionManagement:
    """Test session create/destroy logic."""

    def test_create_session_extracts_session_id(self, connected_specialist, mock_external_client):
        """Test session creation extracts session_id from result."""
        # Mock the sync_call_external_mcp response
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"session_id": "test-session-123"}')]

        with patch('app.src.specialists.navigator_specialist.sync_call_external_mcp', return_value=mock_result):
            session_id = connected_specialist._create_session()

        assert session_id == "test-session-123"

    def test_create_session_returns_none_on_failure(self, connected_specialist):
        """Test session creation returns None on failure."""
        with patch('app.src.specialists.navigator_specialist.sync_call_external_mcp', side_effect=Exception("Connection failed")):
            session_id = connected_specialist._create_session()

        assert session_id is None

    def test_destroy_session_calls_navigator(self, connected_specialist):
        """Test session destruction calls navigator."""
        with patch('app.src.specialists.navigator_specialist.sync_call_external_mcp') as mock_call:
            connected_specialist._destroy_session("test-session-123")

        mock_call.assert_called_once()
        call_args = mock_call.call_args
        assert call_args[0][2] == "session_destroy"
        assert call_args[0][3]["session_id"] == "test-session-123"


# =============================================================================
# TEST: Path/Pattern Extraction
# =============================================================================

class TestPathExtraction:
    """Test path and pattern extraction from user requests."""

    def test_extract_quoted_path(self, navigator_specialist):
        """Test extracting path from quoted string."""
        request = 'Delete the "my-folder" directory'
        path = navigator_specialist._extract_path_from_request(request)
        assert path == "my-folder"

    def test_extract_path_from_folder_phrase(self, navigator_specialist):
        """Test extracting path from 'X folder' phrase."""
        request = "Delete the temp folder"
        path = navigator_specialist._extract_path_from_request(request)
        assert path == "temp"

    def test_extract_path_from_directory_phrase(self, navigator_specialist):
        """Test extracting path from 'X directory' phrase."""
        request = "Remove the old-data directory"
        path = navigator_specialist._extract_path_from_request(request)
        assert path == "old-data"

    def test_extract_pattern_glob(self, navigator_specialist):
        """Test extracting glob pattern."""
        request = "Find files matching *.py"
        pattern = navigator_specialist._extract_pattern_from_request(request)
        assert pattern == "*.py"

    def test_extract_pattern_extension(self, navigator_specialist):
        """Test extracting pattern from '.X files' phrase."""
        request = "Find all .py files"
        pattern = navigator_specialist._extract_pattern_from_request(request)
        assert pattern == "**/*.py"

    def test_extract_pattern_type_name(self, navigator_specialist):
        """Test extracting pattern from file type name."""
        request = "Find all python files"
        pattern = navigator_specialist._extract_pattern_from_request(request)
        assert pattern == "**/*.py"

    def test_extract_pattern_returns_none_for_unclear(self, navigator_specialist):
        """Test pattern extraction returns None for unclear requests."""
        request = "Show me the files"
        pattern = navigator_specialist._extract_pattern_from_request(request)
        assert pattern is None


# =============================================================================
# TEST: Operation Handlers
# =============================================================================

class TestOperationHandlers:
    """Test the operation handler methods."""

    def test_handle_navigator_unavailable(self, navigator_specialist):
        """Test graceful degradation message when navigator unavailable."""
        state = {"messages": [HumanMessage(content="Delete temp")]}
        result = navigator_specialist._handle_navigator_unavailable(state)

        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "Navigator service is currently unavailable" in result["messages"][0].content

    def test_execute_without_request(self, connected_specialist):
        """Test execution with no user message."""
        state = {"messages": []}

        # Mock session management
        with patch.object(connected_specialist, '_create_session', return_value="test-session"):
            with patch.object(connected_specialist, '_destroy_session'):
                result = connected_specialist._execute_logic(state)

        assert "messages" in result
        assert "No request provided" in result["messages"][0].content

    def test_execute_calls_session_lifecycle(self, connected_specialist):
        """Test that execute creates and destroys session."""
        state = {"messages": [HumanMessage(content="List files")]}

        mock_list_result = {"items": ["file1.txt", "file2.txt"]}

        with patch.object(connected_specialist, '_create_session', return_value="test-session") as mock_create:
            with patch.object(connected_specialist, '_destroy_session') as mock_destroy:
                with patch.object(connected_specialist, 'list_directory', return_value=mock_list_result):
                    result = connected_specialist._execute_logic(state)

        mock_create.assert_called_once()
        mock_destroy.assert_called_once_with("test-session")


# =============================================================================
# TEST: Delete Requests
# =============================================================================

class TestDeleteRequests:
    """Test delete operation handling."""

    def test_handle_delete_without_path(self, connected_specialist):
        """Test delete handler when path cannot be determined."""
        result = connected_specialist._handle_delete_request("test-session", "Delete something")

        assert "couldn't determine which directory" in result["messages"][0].content

    def test_handle_delete_success(self, connected_specialist):
        """Test successful delete operation."""
        with patch.object(connected_specialist, 'list_directory', return_value={"items": ["a", "b", "c"]}):
            with patch.object(connected_specialist, 'delete_recursive', return_value={"success": True}):
                result = connected_specialist._handle_delete_request("test-session", 'Delete the "temp" folder')

        assert "Successfully deleted" in result["messages"][0].content
        assert "3 items removed" in result["messages"][0].content

    def test_handle_delete_error(self, connected_specialist):
        """Test delete operation with error."""
        with patch.object(connected_specialist, 'list_directory', return_value={"items": []}):
            with patch.object(connected_specialist, 'delete_recursive', return_value={"error": "Permission denied"}):
                result = connected_specialist._handle_delete_request("test-session", 'Delete the "temp" folder')

        assert "Failed to delete" in result["messages"][0].content
        assert "Permission denied" in result["messages"][0].content


# =============================================================================
# TEST: Find Requests
# =============================================================================

class TestFindRequests:
    """Test find operation handling."""

    def test_handle_find_without_pattern(self, connected_specialist):
        """Test find handler when pattern cannot be determined."""
        result = connected_specialist._handle_find_request("test-session", "Find the files")

        assert "couldn't determine the search pattern" in result["messages"][0].content

    def test_handle_find_success(self, connected_specialist):
        """Test successful find operation."""
        mock_result = {"matches": ["src/main.py", "src/utils.py", "tests/test_main.py"]}

        with patch.object(connected_specialist, 'find_files', return_value=mock_result):
            result = connected_specialist._handle_find_request("test-session", "Find all .py files")

        assert "Found 3 files" in result["messages"][0].content
        assert "**/*.py" in result["messages"][0].content
        assert "navigator_operation" in result.get("artifacts", {})

    def test_handle_find_no_matches(self, connected_specialist):
        """Test find operation with no matches."""
        with patch.object(connected_specialist, 'find_files', return_value={"matches": []}):
            result = connected_specialist._handle_find_request("test-session", "Find *.xyz files")

        assert "No files found" in result["messages"][0].content


# =============================================================================
# TEST: List Requests
# =============================================================================

class TestListRequests:
    """Test list operation handling."""

    def test_handle_list_default_path(self, connected_specialist):
        """Test list with default path."""
        mock_result = {"items": ["file1.txt", "folder1"]}

        with patch.object(connected_specialist, 'list_directory', return_value=mock_result) as mock_list:
            result = connected_specialist._handle_list_request("test-session", "List files")

        mock_list.assert_called_once_with("test-session", ".")
        assert "2 items" in result["messages"][0].content

    def test_handle_list_specific_path(self, connected_specialist):
        """Test list with specific path."""
        mock_result = {"items": ["main.py", "utils.py"]}

        with patch.object(connected_specialist, 'list_directory', return_value=mock_result) as mock_list:
            result = connected_specialist._handle_list_request("test-session", 'List the "src" directory')

        mock_list.assert_called_once_with("test-session", "src")
        assert "src" in result["messages"][0].content

    def test_handle_list_empty_directory(self, connected_specialist):
        """Test list on empty directory."""
        with patch.object(connected_specialist, 'list_directory', return_value={"items": []}):
            result = connected_specialist._handle_list_request("test-session", "List files")

        assert "is empty" in result["messages"][0].content


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
        assert call_args[0][0] == "navigator_specialist"

        services = call_args[0][1]
        assert "delete_recursive" in services
        assert "find_files" in services
        assert "list_directory" in services
        assert "is_available" in services

    def test_mcp_is_available(self, connected_specialist):
        """Test is_available MCP service."""
        assert connected_specialist._mcp_is_available() is True

    def test_mcp_is_available_when_not_connected(self, navigator_specialist, mock_external_client):
        """Test is_available returns False when client injected but not connected."""
        mock_external_client.is_connected.return_value = False
        navigator_specialist.external_mcp_client = mock_external_client
        assert navigator_specialist._mcp_is_available() is False

    def test_mcp_is_available_when_client_not_injected(self, navigator_specialist):
        """Test is_available returns True when client not yet injected (allows loading)."""
        assert navigator_specialist._mcp_is_available() is True


# =============================================================================
# TEST: Result Parsing
# =============================================================================

class TestResultParsing:
    """Test result parsing from navigator responses."""

    def test_parse_json_result(self, navigator_specialist):
        """Test parsing JSON result."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"key": "value"}')]

        parsed = navigator_specialist._parse_result(mock_result)

        assert parsed == {"key": "value"}

    def test_parse_non_json_result(self, navigator_specialist):
        """Test parsing non-JSON result."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='Plain text response')]

        parsed = navigator_specialist._parse_result(mock_result)

        assert parsed == {"content": "Plain text response"}

    def test_parse_none_result(self, navigator_specialist):
        """Test parsing None result."""
        parsed = navigator_specialist._parse_result(None)

        assert "error" in parsed

    def test_extract_session_id(self, navigator_specialist):
        """Test session ID extraction."""
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text='{"session_id": "abc-123"}')]

        session_id = navigator_specialist._extract_session_id(mock_result)

        assert session_id == "abc-123"
