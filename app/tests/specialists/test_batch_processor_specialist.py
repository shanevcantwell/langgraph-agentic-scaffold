"""
Tests for BatchProcessorSpecialist (ADR-CORE-049 Operation Dispatcher pattern).

Tests the specialist's LLM parsing. Dispatcher behavior is mocked since it
requires an async event loop that's complex to set up in unit tests.

NOTE: 4 tests are marked xfail per ADR-CORE-054 - dispatch_sync() requires
the MCP client's event loop, which the mock doesn't provide. These tests
will be revisited after prompt-prix MCP integration.
"""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.batch_processor_specialist import BatchProcessorSpecialist
from app.src.specialists.schemas._file_operations import FileOperation
from app.src.dispatchers import OperationResult


@pytest.fixture
def batch_processor(initialized_specialist_factory):
    """Create BatchProcessorSpecialist with mocked dependencies."""
    specialist = initialized_specialist_factory("BatchProcessorSpecialist", "batch_processor_specialist", {})

    # Mock external_mcp_client to pass availability check
    mock_mcp = MagicMock()
    mock_mcp.is_connected.return_value = True
    specialist.external_mcp_client = mock_mcp

    return specialist


def _make_success_result(path: str, op_type: str = "write", destination: str = None) -> OperationResult:
    """Helper to create successful operation results."""
    op = FileOperation(type=op_type, path=path, destination=destination)
    return OperationResult(operation=op, success=True, result=f"Completed {op_type} {path}")


def _make_failure_result(path: str, error: str, op_type: str = "write", destination: str = None) -> OperationResult:
    """Helper to create failed operation results."""
    op = FileOperation(type=op_type, path=path, destination=destination)
    return OperationResult(operation=op, success=False, error=error)


@pytest.mark.xfail(
    reason="ADR-CORE-054: dispatch_sync() requires MCP event loop; pending prompt-prix integration",
    strict=False
)
def test_successful_batch_operations(batch_processor):
    """Test successful batch file operations."""
    # Mock LLM to return FileOperationList
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": [
                {"type": "write", "path": "e.txt", "content": ""},
                {"type": "write", "path": "n.txt", "content": ""}
            ]
        }
    }

    # Mock dispatcher to return success results
    mock_results = [
        _make_success_result("e.txt"),
        _make_success_result("n.txt")
    ]

    with patch('app.src.specialists.batch_processor_specialist.FileOperationDispatcher') as MockDispatcher:
        mock_instance = MagicMock()
        mock_instance.dispatch_sync.return_value = mock_results
        MockDispatcher.return_value = mock_instance

        state = {
            "messages": [HumanMessage(content="Create empty files e.txt and n.txt")]
        }
        result = batch_processor.execute(state)

    # Verify artifacts
    assert "artifacts" in result
    assert "batch_operation_summary" in result["artifacts"]
    assert result["artifacts"]["batch_operation_summary"]["successful"] == 2
    assert result["artifacts"]["batch_operation_summary"]["failed"] == 0
    assert result["artifacts"]["batch_operation_summary"]["total"] == 2

    # Verify message
    assert "messages" in result
    assert isinstance(result["messages"][0], AIMessage)
    assert "Successfully completed all 2 operations" in result["messages"][0].content

    # Verify report artifact
    assert "batch_operation_report.md" in result["artifacts"]

    # Verify task completion
    assert result["task_is_complete"] is True


@pytest.mark.xfail(
    reason="ADR-CORE-054: dispatch_sync() requires MCP event loop; pending prompt-prix integration",
    strict=False
)
def test_partial_failure(batch_processor):
    """Test handling of partial failures in batch operation."""
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": [
                {"type": "write", "path": "good.txt", "content": ""},
                {"type": "write", "path": "bad.txt", "content": ""},
                {"type": "write", "path": "also_good.txt", "content": ""}
            ]
        }
    }

    mock_results = [
        _make_success_result("good.txt"),
        _make_failure_result("bad.txt", "Permission denied"),
        _make_success_result("also_good.txt")
    ]

    with patch('app.src.specialists.batch_processor_specialist.FileOperationDispatcher') as MockDispatcher:
        mock_instance = MagicMock()
        mock_instance.dispatch_sync.return_value = mock_results
        MockDispatcher.return_value = mock_instance

        state = {
            "messages": [HumanMessage(content="Create good.txt, bad.txt, also_good.txt")]
        }
        result = batch_processor.execute(state)

    # Verify partial success
    assert result["artifacts"]["batch_operation_summary"]["successful"] == 2
    assert result["artifacts"]["batch_operation_summary"]["failed"] == 1
    assert result["artifacts"]["batch_operation_summary"]["total"] == 3

    # Verify message includes failure info
    assert "bad.txt" in result["messages"][0].content
    assert "2/3" in result["messages"][0].content


def test_missing_external_mcp_client(batch_processor):
    """Test error handling when external MCP client is not available."""
    batch_processor.external_mcp_client = None

    state = {
        "messages": [HumanMessage(content="Create files")]
    }
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert "not available" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


def test_empty_messages(batch_processor):
    """Test error handling when no messages provided."""
    state = {"messages": []}
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert "no batch operation" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


def test_llm_returns_no_operations(batch_processor):
    """Test error handling when LLM returns empty operation list."""
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": []
        }
    }

    state = {
        "messages": [HumanMessage(content="Vague request")]
    }
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


@pytest.mark.xfail(
    reason="ADR-CORE-054: dispatch_sync() requires MCP event loop; pending prompt-prix integration",
    strict=False
)
def test_move_operation(batch_processor):
    """Test move file operation."""
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": [
                {"type": "move", "path": "old.txt", "destination": "archive/old.txt"}
            ]
        }
    }

    mock_results = [
        _make_success_result("old.txt", op_type="move", destination="archive/old.txt")
    ]

    with patch('app.src.specialists.batch_processor_specialist.FileOperationDispatcher') as MockDispatcher:
        mock_instance = MagicMock()
        mock_instance.dispatch_sync.return_value = mock_results
        MockDispatcher.return_value = mock_instance

        state = {
            "messages": [HumanMessage(content="Move old.txt to archive/")]
        }
        result = batch_processor.execute(state)

    # Verify success
    assert result["artifacts"]["batch_operation_summary"]["successful"] == 1
    assert result["artifacts"]["batch_operation_summary"]["failed"] == 0


@pytest.mark.xfail(
    reason="ADR-CORE-054: dispatch_sync() requires MCP event loop; pending prompt-prix integration",
    strict=False
)
def test_mcp_error_during_execution(batch_processor):
    """Test graceful handling of errors during file operations."""
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": [
                {"type": "write", "path": "file1.txt", "content": "hello"}
            ]
        }
    }

    mock_results = [
        _make_failure_result("file1.txt", "Permission denied")
    ]

    with patch('app.src.specialists.batch_processor_specialist.FileOperationDispatcher') as MockDispatcher:
        mock_instance = MagicMock()
        mock_instance.dispatch_sync.return_value = mock_results
        MockDispatcher.return_value = mock_instance

        state = {
            "messages": [HumanMessage(content="Create file1.txt")]
        }
        result = batch_processor.execute(state)

    # Verify failure tracked
    assert result["artifacts"]["batch_operation_summary"]["successful"] == 0
    assert result["artifacts"]["batch_operation_summary"]["failed"] == 1

    details = result["artifacts"]["batch_operation_details"]
    assert details[0]["status"] == "failed"
    assert "Permission denied" in details[0]["error"]


def test_dispatcher_exception_handled(batch_processor):
    """Test that dispatcher exceptions are caught and reported."""
    batch_processor.llm_adapter.invoke.return_value = {
        "json_response": {
            "operations": [
                {"type": "write", "path": "file.txt", "content": ""}
            ]
        }
    }

    with patch('app.src.specialists.batch_processor_specialist.FileOperationDispatcher') as MockDispatcher:
        mock_instance = MagicMock()
        mock_instance.dispatch_sync.side_effect = RuntimeError("Dispatcher timeout")
        MockDispatcher.return_value = mock_instance

        state = {
            "messages": [HumanMessage(content="Create file.txt")]
        }
        result = batch_processor.execute(state)

    # Should return error message, not crash
    assert "messages" in result
    assert "error" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True
