# app/tests/unit/test_file_specialist.py

import pytest
import os
import shutil
from uuid import uuid4
from pathlib import Path

from app.src.specialists.file_specialist import FileSpecialist
from app.src.specialists.schemas._file_ops import (
    CreateDirectoryParams,
    WriteFileParams,
    CreateZipFromDirectoryParams,
)
from app.src.utils.errors import SpecialistError
from langchain_core.messages import ToolMessage, HumanMessage

# --- Architectural Note ---
# This test suite validates the FileSpecialist in its refactored role as a
# PROCEDURAL TOOL DISPATCHER. Unlike its predecessor, this specialist does not
# invoke an LLM. Its primary responsibility is to receive a `ToolMessage` from
# an upstream planner and execute the corresponding deterministic file operation.
#
# Therefore, these tests focus on two areas:
# 1. The correctness of the internal file operation methods (e.g., _write_file).
# 2. The correctness of the main `_execute_logic` dispatcher.

@pytest.fixture
def file_specialist_instance(initialized_specialist_factory):
    """Provides a clean FileSpecialist instance for each test."""
    return initialized_specialist_factory("FileSpecialist", "file_specialist")

# === Group 1: Internal Method Logic Tests ===
# These tests validate the core business logic of each file operation.

def test_create_directory(file_specialist_instance, tmp_path: Path):
    """Tests the internal _create_directory method."""
    dir_path = tmp_path / "new_dir"
    status = file_specialist_instance._create_directory(str(dir_path))
    assert dir_path.is_dir()
    assert "Successfully created directory" in status

def test_write_file(file_specialist_instance, tmp_path: Path):
    """Tests the internal _write_file method with both string and bytes content."""
    # Test with string
    file_path_str = tmp_path / "test.txt"
    status_str = file_specialist_instance._write_file(str(file_path_str), "hello")
    assert file_path_str.read_text() == "hello"
    assert "Successfully wrote file" in status_str

    # Test with bytes
    file_path_bytes = tmp_path / "test.bin"
    status_bytes = file_specialist_instance._write_file(str(file_path_bytes), b"world")
    assert file_path_bytes.read_bytes() == b"world"
    assert "Successfully wrote file" in status_bytes

def test_write_file_empty_content(file_specialist_instance, tmp_path: Path):
    """Tests that writing an empty file is handled correctly."""
    file_path = tmp_path / "empty.txt"
    file_specialist_instance._write_file(str(file_path), "")
    assert file_path.exists()
    assert file_path.read_text() == ""

def test_create_zip_from_directory(file_specialist_instance, tmp_path: Path):
    """Tests the internal _create_zip_from_directory method."""
    source_dir = tmp_path / "source_dir"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("zip content")
    dest_path = tmp_path / "archive.zip"

    status = file_specialist_instance._create_zip_from_directory(str(source_dir), str(dest_path))

    assert dest_path.is_file()
    assert "Successfully created zip archive" in status

    # For extra confidence, unpack the archive and verify its contents
    shutil.unpack_archive(str(dest_path), tmp_path / "unpacked")
    assert (tmp_path / "unpacked" / "file.txt").read_text() == "zip content"

# === Group 2: Main Dispatcher Logic Tests (_execute_logic) ===
# These tests validate the specialist's main entry point and its ability to
# correctly interpret and dispatch incoming ToolMessages.

@pytest.mark.parametrize("tool_name, tool_args, test_id", [
    ("CreateDirectoryParams", {"path": "new_dir"}, "create_dir"),
    ("WriteFileParams", {"path": "new_file.txt", "content": "content"}, "write_file"),
    ("CreateZipFromDirectoryParams", {"source_path": "src_dir", "destination_path": "archive.zip"}, "create_zip"),
])
def test_execute_logic_success_dispatch(file_specialist_instance, tmp_path: Path, tool_name, tool_args, test_id):
    """
    Tests that _execute_logic correctly dispatches various tool calls
    and executes them successfully.
    """
    # Adjust paths to be absolute for the test execution environment
    if "path" in tool_args:
        tool_args["path"] = str(tmp_path / tool_args["path"])
    if "source_path" in tool_args:
        source_path = tmp_path / tool_args["source_path"]
        source_path.mkdir()
        (source_path / "dummy.txt").touch()
        tool_args["source_path"] = str(source_path)
    if "destination_path" in tool_args:
        tool_args["destination_path"] = str(tmp_path / tool_args["destination_path"])

    tool_call_id = str(uuid4())
    state = {
        "messages": [
            ToolMessage(
                name=tool_name,
                content="", # Content is ignored by the dispatcher
                tool_call_id=tool_call_id,
                additional_kwargs={"parsed_args": tool_args}
            )
        ]
    }

    result_state = file_specialist_instance._execute_logic(state)

    assert "messages" in result_state
    response_message = result_state["messages"][0]
    assert isinstance(response_message, ToolMessage)
    assert response_message.tool_call_id == tool_call_id
    assert "Successfully" in response_message.content

def test_execute_logic_handles_unknown_tool(file_specialist_instance):
    """Tests that an unknown tool call is handled gracefully with a clear message."""
    tool_call_id = str(uuid4())
    state = {
        "messages": [
            ToolMessage(
                name="UnknownTool",
                content="",
                tool_call_id=tool_call_id,
                additional_kwargs={"parsed_args": {}}
            )
        ]
    }
    result_state = file_specialist_instance._execute_logic(state)
    response_message = result_state["messages"][0]
    assert "Unknown tool 'UnknownTool'" in response_message.content

def test_execute_logic_handles_tool_execution_error(file_specialist_instance):
    """Tests that a SpecialistError during tool execution is caught and reported."""
    # Attempt to write to a path that will cause a permission error.
    # On most systems, writing to the root directory is not allowed.
    tool_args = {"path": "/", "content": "test"}
    tool_call_id = str(uuid4())
    state = {
        "messages": [
            ToolMessage(
                name="WriteFileParams",
                content="",
                tool_call_id=tool_call_id,
                additional_kwargs={"parsed_args": tool_args}
            )
        ]
    }
    result_state = file_specialist_instance._execute_logic(state)
    response_message = result_state["messages"][0]
    assert "Error writing file" in response_message.content

def test_execute_logic_ignores_non_tool_message(file_specialist_instance):
    """
    Tests that the specialist does nothing if the last message is not a ToolMessage,
    adhering to its procedural contract.
    """
    state = {"messages": [HumanMessage(content="This is not a tool call.")]}
    result_state = file_specialist_instance._execute_logic(state)
    assert result_state == {}

