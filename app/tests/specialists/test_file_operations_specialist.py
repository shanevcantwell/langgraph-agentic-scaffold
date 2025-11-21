"""
Tests for FileOperationsSpecialist - User interface layer for file operations.

This specialist interprets user requests and routes to FileSpecialist via MCP,
maintaining architectural separation between interface and service layers.
"""
import pytest
from unittest.mock import Mock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage

from app.src.specialists.file_operations_specialist import FileOperationsSpecialist


class TestFileOperationsSpecialist:
    """Test suite for FileOperationsSpecialist."""

    def test_init(self, initialized_specialist_factory):
        """Test FileOperationsSpecialist initializes correctly."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")
        assert specialist is not None
        assert specialist.specialist_name == "file_operations_specialist"
        assert isinstance(specialist, FileOperationsSpecialist)

    def test_list_files_operation(self, initialized_specialist_factory):
        """Test listing files via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter to return list_files operation
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "list_files",
                    "path": "."
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = ["file1.txt", "file2.py", "folder/"]

        # Execute
        state = {
            "messages": [HumanMessage(content="List all files in the workspace")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "list_files",
            path="."
        )

        # Verify response
        assert "messages" in result
        assert len(result["messages"]) == 1
        assert "file1.txt" in result["messages"][0].content
        assert "file2.py" in result["messages"][0].content
        assert result["task_is_complete"] is True

    def test_read_file_operation(self, initialized_specialist_factory):
        """Test reading file contents via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "read_file",
                    "path": "config.json"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = '{"setting": "value"}'

        # Execute
        state = {
            "messages": [HumanMessage(content="Show me what's in config.json")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "read_file",
            path="config.json"
        )

        # Verify response contains file content
        assert "messages" in result
        assert '{"setting": "value"}' in result["messages"][0].content
        assert "config.json" in result["messages"][0].content

    def test_write_file_operation(self, initialized_specialist_factory):
        """Test writing file via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "write_file",
                    "path": "test.txt",
                    "content": "Hello World"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = "Successfully wrote file: test.txt (11 chars)"

        # Execute
        state = {
            "messages": [HumanMessage(content="Create test.txt with Hello World")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "write_file",
            path="test.txt",
            content="Hello World"
        )

        # Verify success response
        assert "messages" in result
        assert "Successfully wrote" in result["messages"][0].content
        assert result["task_is_complete"] is True

    def test_create_directory_operation(self, initialized_specialist_factory):
        """Test creating directory via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "create_directory",
                    "path": "output"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = "Successfully created directory: output"

        # Execute
        state = {
            "messages": [HumanMessage(content="Make a folder called output")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "create_directory",
            path="output"
        )

        # Verify response
        assert "Successfully created" in result["messages"][0].content

    def test_delete_file_operation(self, initialized_specialist_factory):
        """Test deleting file via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "delete_file",
                    "path": "temp.txt"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = "Successfully deleted file: temp.txt"

        # Execute
        state = {
            "messages": [HumanMessage(content="Delete temp.txt")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "delete_file",
            path="temp.txt"
        )

        # Verify response
        assert "Successfully deleted" in result["messages"][0].content

    def test_rename_file_operation(self, initialized_specialist_factory):
        """Test renaming file via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "rename_file",
                    "old_path": "old.txt",
                    "new_path": "new.txt"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = "Successfully renamed file: old.txt -> new.txt"

        # Execute
        state = {
            "messages": [HumanMessage(content="Rename old.txt to new.txt")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "rename_file",
            old_path="old.txt",
            new_path="new.txt"
        )

        # Verify response
        assert "Successfully renamed" in result["messages"][0].content

    def test_no_mcp_client_error(self, initialized_specialist_factory):
        """Test error handling when MCP client not available."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")
        specialist.mcp_client = None

        # Mock LLM adapter (shouldn't be called)
        specialist.llm_adapter = Mock()

        # Execute
        state = {
            "messages": [HumanMessage(content="List files")]
        }
        result = specialist._execute_logic(state)

        # Verify error response
        assert "messages" in result
        assert "not available" in result["messages"][0].content.lower()
        assert result["task_is_complete"] is True

    def test_no_tool_calls_from_llm(self, initialized_specialist_factory):
        """Test handling when LLM doesn't return tool calls."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter returning no tool calls
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": []
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client (shouldn't be called)
        specialist.mcp_client = Mock()

        # Execute
        state = {
            "messages": [HumanMessage(content="Do something vague")]
        }
        result = specialist._execute_logic(state)

        # Verify error response
        assert "messages" in result
        assert "couldn't determine" in result["messages"][0].content.lower()
        assert result["task_is_complete"] is True
        specialist.mcp_client.call.assert_not_called()

    def test_mcp_call_failure(self, initialized_specialist_factory):
        """Test error handling when MCP call fails."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "read_file",
                    "path": "nonexistent.txt"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client to raise error
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.side_effect = Exception("File not found: nonexistent.txt")

        # Execute
        state = {
            "messages": [HumanMessage(content="Read nonexistent.txt")]
        }
        result = specialist._execute_logic(state)

        # Verify error is handled gracefully
        assert "messages" in result
        assert "Error" in result["messages"][0].content
        assert "File not found" in result["messages"][0].content
        assert result["task_is_complete"] is True

    def test_empty_file_list_response(self, initialized_specialist_factory):
        """Test handling of empty directory."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "list_files",
                    "path": "empty_folder"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client returning empty list
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = []

        # Execute
        state = {
            "messages": [HumanMessage(content="List files in empty_folder")]
        }
        result = specialist._execute_logic(state)

        # Verify response indicates empty directory
        assert "messages" in result
        assert "No files found" in result["messages"][0].content
        assert "empty_folder" in result["messages"][0].content

    def test_append_to_file_operation(self, initialized_specialist_factory):
        """Test appending content to file via MCP."""
        specialist = initialized_specialist_factory("FileOperationsSpecialist")

        # Mock LLM adapter
        mock_adapter = Mock()
        mock_adapter.invoke.return_value = {
            "tool_calls": [{
                "name": "FileOperation",
                "args": {
                    "operation": "append_to_file",
                    "path": "log.txt",
                    "content": "\nNew log entry"
                }
            }]
        }
        specialist.llm_adapter = mock_adapter

        # Mock MCP client
        specialist.mcp_client = Mock()
        specialist.mcp_client.call.return_value = "Successfully appended to file: log.txt (14 chars)"

        # Execute
        state = {
            "messages": [HumanMessage(content="Add 'New log entry' to log.txt")]
        }
        result = specialist._execute_logic(state)

        # Verify MCP call
        specialist.mcp_client.call.assert_called_once_with(
            "file_specialist",
            "append_to_file",
            path="log.txt",
            content="\nNew log entry"
        )

        # Verify response
        assert "Successfully appended" in result["messages"][0].content
