"""
Tests for BatchProcessorSpecialist.
"""
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.batch_processor_specialist import BatchProcessorSpecialist
from app.src.specialists.schemas._batch_ops import BatchSortPlan, FileSortDecision


@pytest.fixture
def batch_processor(initialized_specialist_factory):
    """Create BatchProcessorSpecialist with mocked dependencies."""
    specialist = initialized_specialist_factory("BatchProcessorSpecialist", "batch_processor_specialist", {})
    specialist.mcp_client = MagicMock()
    return specialist


def test_successful_batch_sort(batch_processor):
    """Test successful batch sorting of all files."""
    # Mock LLM adapter for two-phase approach
    batch_processor.llm_adapter.invoke.side_effect = [
        # Phase 1: Parse batch request
        {
            "tool_calls": [{
                "name": "BatchSortRequest",
                "args": {
                    "file_paths": ["e.txt", "n.txt"],
                    "destination_directories": ["a-m/", "n-z/"],
                    "strategy": {"strategy": "emergent", "read_content": False}
                }
            }]
        },
        # Phase 2: Generate sort plan
        {
            "parsed_output": BatchSortPlan(decisions=[
                FileSortDecision(
                    file_path="e.txt",
                    destination="a-m/",
                    rationale="Starts with e (falls in a-m range)"
                ),
                FileSortDecision(
                    file_path="n.txt",
                    destination="n-z/",
                    rationale="Starts with n (falls in n-z range)"
                )
            ])
        }
    ]

    # Mock MCP client calls
    batch_processor.mcp_client.call.side_effect = [
        True,  # file_exists e.txt
        True,  # file_exists n.txt
        True,  # file_exists e.txt (in execute phase)
        None,  # create_directory a-m/
        "Successfully renamed e.txt",  # rename e.txt
        True,  # file_exists n.txt (in execute phase)
        None,  # create_directory n-z/
        "Successfully renamed n.txt"   # rename n.txt
    ]

    # Execute
    state = {
        "messages": [HumanMessage(content="Sort e.txt and n.txt into a-m/ and n-z/")]
    }
    result = batch_processor.execute(state)

    # Verify
    assert "artifacts" in result
    assert result["artifacts"]["batch_sort_summary"]["successful"] == 2
    assert result["artifacts"]["batch_sort_summary"]["failed"] == 0
    assert result["artifacts"]["batch_sort_summary"]["total_files"] == 2

    # Verify message
    assert "messages" in result
    assert isinstance(result["messages"][0], AIMessage)
    assert "Successfully sorted all 2 files" in result["messages"][0].content

    # Verify details
    assert len(result["artifacts"]["batch_sort_details"]) == 2
    assert all(item["status"] == "success" for item in result["artifacts"]["batch_sort_details"])

    # Verify report
    assert "batch_sort_report.md" in result["artifacts"]
    assert "Batch File Sort Report" in result["artifacts"]["batch_sort_report.md"]
    assert "100%" in result["artifacts"]["batch_sort_report.md"]  # 100% success rate

    # Verify task completion
    assert result["task_is_complete"] is True


def test_partial_failure(batch_processor):
    """Test handling of partial failures in batch operation."""
    # Mock LLM adapter
    batch_processor.llm_adapter.invoke.side_effect = [
        # Phase 1: Parse batch request
        {
            "tool_calls": [{
                "name": "BatchSortRequest",
                "args": {
                    "file_paths": ["e.txt", "missing.txt", "n.txt"],
                    "destination_directories": ["a-m/", "n-z/"],
                    "strategy": {"strategy": "emergent", "read_content": False}
                }
            }]
        },
        # Phase 2: Generate sort plan
        {
            "parsed_output": BatchSortPlan(decisions=[
                FileSortDecision(file_path="e.txt", destination="a-m/", rationale="Starts with e"),
                FileSortDecision(file_path="missing.txt", destination="a-m/", rationale="Starts with m"),
                FileSortDecision(file_path="n.txt", destination="n-z/", rationale="Starts with n")
            ])
        }
    ]

    # Mock MCP client - middle file doesn't exist
    batch_processor.mcp_client.call.side_effect = [
        True,   # file_exists e.txt (gather context)
        False,  # file_exists missing.txt (gather context)
        True,   # file_exists n.txt (gather context)
        True,   # file_exists e.txt (execute)
        None,   # create_directory a-m/
        "Success",  # rename e.txt
        False,  # file_exists missing.txt (execute) - FAILS HERE
        True,   # file_exists n.txt (execute)
        None,   # create_directory n-z/
        "Success"   # rename n.txt
    ]

    # Execute
    state = {
        "messages": [HumanMessage(content="Sort e.txt, missing.txt, and n.txt")]
    }
    result = batch_processor.execute(state)

    # Verify partial success
    assert result["artifacts"]["batch_sort_summary"]["successful"] == 2
    assert result["artifacts"]["batch_sort_summary"]["failed"] == 1
    assert result["artifacts"]["batch_sort_summary"]["total_files"] == 3

    # Verify message includes failure info
    assert "missing.txt" in result["messages"][0].content
    assert "2/3" in result["messages"][0].content

    # Verify details include both successes and failures
    details = result["artifacts"]["batch_sort_details"]
    successes = [d for d in details if d["status"] == "success"]
    failures = [d for d in details if d["status"] == "failed"]

    assert len(successes) == 2
    assert len(failures) == 1
    assert failures[0]["file"] == "missing.txt"
    assert failures[0]["error"] == "File not found"


def test_missing_mcp_client(batch_processor):
    """Test error handling when MCP client is not available."""
    batch_processor.mcp_client = None

    state = {
        "messages": [HumanMessage(content="Sort files")]
    }
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert "service not available" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


def test_empty_messages(batch_processor):
    """Test error handling when no messages provided."""
    state = {"messages": []}
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert "no batch operation request" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


def test_llm_parse_failure(batch_processor):
    """Test error handling when LLM cannot parse request."""
    # Mock LLM returning no tool calls
    batch_processor.llm_adapter.invoke.return_value = {"tool_calls": []}

    state = {
        "messages": [HumanMessage(content="Vague request")]
    }
    result = batch_processor.execute(state)

    assert "error" in result["messages"][0].content.lower()
    assert result["task_is_complete"] is True


def test_batch_sort_with_content_reading(batch_processor):
    """Test batch sorting with content reading enabled."""
    # Mock LLM adapter
    batch_processor.llm_adapter.invoke.side_effect = [
        # Phase 1: Parse batch request with read_content=True
        {
            "tool_calls": [{
                "name": "BatchSortRequest",
                "args": {
                    "file_paths": ["doc1.txt"],
                    "destination_directories": ["docs/"],
                    "strategy": {"strategy": "emergent", "read_content": True}
                }
            }]
        },
        # Phase 2: Generate sort plan
        {
            "parsed_output": BatchSortPlan(decisions=[
                FileSortDecision(
                    file_path="doc1.txt",
                    destination="docs/",
                    rationale="Contains documentation content"
                )
            ])
        }
    ]

    # Mock MCP client - includes read_file call
    batch_processor.mcp_client.call.side_effect = [
        True,  # file_exists doc1.txt (gather context)
        "This is documentation content",  # read_file doc1.txt
        True,  # file_exists doc1.txt (execute)
        None,  # create_directory docs/
        "Success"  # rename doc1.txt
    ]

    # Execute
    state = {
        "messages": [HumanMessage(content="Sort doc1.txt by reading its content")]
    }
    result = batch_processor.execute(state)

    # Verify success
    assert result["artifacts"]["batch_sort_summary"]["successful"] == 1
    assert result["artifacts"]["batch_sort_summary"]["failed"] == 0

    # Verify read_file was called during context gathering
    # Should have 5 MCP calls: file_exists, read_file, file_exists, create_directory, rename
    assert batch_processor.mcp_client.call.call_count == 5

    # Verify second call was read_file
    second_call_args = batch_processor.mcp_client.call.call_args_list[1][0]
    assert second_call_args[0] == "file_specialist"
    assert second_call_args[1] == "read_file"


def test_mcp_error_during_execution(batch_processor):
    """Test graceful handling of MCP errors during file operations."""
    # Mock LLM adapter
    batch_processor.llm_adapter.invoke.side_effect = [
        # Phase 1: Parse
        {
            "tool_calls": [{
                "name": "BatchSortRequest",
                "args": {
                    "file_paths": ["file1.txt"],
                    "destination_directories": ["dest/"],
                    "strategy": {"strategy": "emergent", "read_content": False}
                }
            }]
        },
        # Phase 2: Plan
        {
            "parsed_output": BatchSortPlan(decisions=[
                FileSortDecision(file_path="file1.txt", destination="dest/", rationale="Test")
            ])
        }
    ]

    # Mock MCP client with error during rename
    batch_processor.mcp_client.call.side_effect = [
        True,  # file_exists (gather context)
        True,  # file_exists (execute)
        None,  # create_directory
        Exception("Permission denied")  # rename - FAILS HERE
    ]

    # Execute
    state = {
        "messages": [HumanMessage(content="Sort file1.txt")]
    }
    result = batch_processor.execute(state)

    # Verify failure tracked
    assert result["artifacts"]["batch_sort_summary"]["successful"] == 0
    assert result["artifacts"]["batch_sort_summary"]["failed"] == 1

    details = result["artifacts"]["batch_sort_details"]
    assert details[0]["status"] == "failed"
    assert "Permission denied" in details[0]["error"]
