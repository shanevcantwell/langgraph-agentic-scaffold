# Audit Date: Sept 23, 2025
import pytest
import os
from unittest.mock import patch, MagicMock, mock_open

from app.src.specialists.file_specialist import FileSpecialist, ReadFileParams, WriteFileParams, ListDirectoryParams
from app.src.utils.errors import SpecialistError, LLMInvocationError
from langchain_core.messages import HumanMessage, AIMessage

# Architectural Note: The 'tmp_path' fixture is provided by pytest.
# It creates a unique temporary directory for each test function, ensuring that
# tests are isolated and do not interfere with each other or leave artifacts
# on the filesystem. This is the standard best practice for testing file I/O.

@pytest.fixture
def mock_config_loader():
    """Mocks the ConfigLoader to prevent file system access during tests."""
    with patch('app.src.utils.config_loader.ConfigLoader') as mock_loader:
        mock_loader.return_value.get_specialist_config.return_value = {
            "root_dir": "./test_workspace",
            "prompt_file": "fake_prompt.md"
        }
        mock_loader.return_value.get_provider_config.return_value = {}
        yield mock_loader

@pytest.fixture
def mock_adapter_factory():
    """Mocks the AdapterFactory to prevent LLM client instantiation."""
    with patch('app.src.llm.factory.AdapterFactory') as mock_factory:
        yield mock_factory

@pytest.fixture
def mock_load_prompt():
    """Mocks the prompt loader."""
    with patch('app.src.utils.prompt_loader.load_prompt') as mock_load:
        mock_load.return_value = "Fake system prompt"
        yield mock_load

@pytest.fixture
def file_specialist(tmp_path, mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Provides a FileSpecialist instance with a temporary workspace."""
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    
    mock_config_loader.return_value.get_specialist_config.return_value['root_dir'] = str(workspace)
    
    specialist = FileSpecialist(specialist_name="file_specialist")
    assert specialist.root_dir == str(workspace)
    return specialist

def test_get_full_path_success(file_specialist, tmp_path):
    """Tests that a valid relative path is resolved correctly."""
    workspace = tmp_path / "test_workspace"
    expected_path = os.path.abspath(str(workspace / "test.txt"))
    resolved_path = file_specialist._get_full_path("test.txt")
    assert resolved_path == expected_path

def test_get_full_path_traversal_denied(file_specialist):
    """Tests that directory traversal using '..' is blocked."""
    with pytest.raises(SpecialistError, match="Only relative paths are allowed"):
        file_specialist._get_full_path("../secret.txt")

def test_get_full_path_absolute_path_denied(file_specialist):
    """Tests that absolute paths are blocked."""
    with pytest.raises(SpecialistError, match="Only relative paths are allowed"):
        file_specialist._get_full_path("/etc/passwd")

def test_read_file_success(file_specialist, tmp_path):
    """Tests successful file reading via the internal method."""
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    test_file.write_text("Hello, world!")
    
    params = ReadFileParams(file_path="test.txt")
    content, status = file_specialist._read_file(params)
    
    assert content == "Hello, world!"
    assert "Successfully read" in status

def test_read_file_not_found(file_specialist):
    """Tests reading a file that does not exist."""
    params = ReadFileParams(file_path="non_existent_file.txt")
    content, status = file_specialist._read_file(params)
    
    assert content is None
    assert "Error reading file" in status

def test_read_file_empty(file_specialist, tmp_path):
    """Tests reading a file that is empty."""
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    test_file.touch() # Create an empty file

    params = ReadFileParams(file_path="test.txt")
    content, status = file_specialist._read_file(params)

    assert content == ""
    assert "Successfully read" in status

def test_write_file_safety_on(file_specialist, tmp_path):
    """Tests that file writing is mocked when safety is ON (default)."""
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    
    file_specialist.is_safety_on = True # Explicitly set for test clarity

    params = WriteFileParams(file_path="test.txt", content="new content")
    status = file_specialist._write_file(params)
    
    # Assert that the file was NOT created.
    assert not test_file.exists()
    assert "DRY RUN" in status
    assert "Would have written content" in status

def test_write_file_safety_off(file_specialist, tmp_path):
    """Tests that file writing proceeds when safety is OFF."""
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    file_specialist.is_safety_on = False # Explicitly disable safety for this test
    params = WriteFileParams(file_path="test.txt", content="new content")
    status = file_specialist._write_file(params)
    assert test_file.exists()
    assert test_file.read_text() == "new content"
    assert "Successfully wrote" in status

def test_write_file_safety_off_overwrites_existing_file(file_specialist, tmp_path):
    """Tests that writing to an existing file overwrites its content when safety is off."""
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    test_file.write_text("initial content")

    file_specialist.is_safety_on = False
    params = WriteFileParams(file_path="test.txt", content="overwritten content")
    status = file_specialist._write_file(params)

    assert test_file.read_text() == "overwritten content"
    assert "Successfully wrote" in status

def test_write_file_permission_error(file_specialist):
    """Tests that a permission error during writing is handled gracefully."""
    file_specialist.is_safety_on = False
    params = WriteFileParams(file_path="protected/file.txt", content="some content")

    with patch("builtins.open", mock_open()) as mocked_open:
        mocked_open.side_effect = PermissionError("Permission denied")
        status = file_specialist._write_file(params)
        assert "Error writing file" in status
        assert "Permission denied" in status

def test_list_directory_success(file_specialist, tmp_path):
    """Tests successful directory listing."""
    workspace = tmp_path / "test_workspace"
    (workspace / "file1.txt").touch()
    (workspace / "subdir").mkdir()
    (workspace / "subdir" / "file2.txt").touch()
    
    params = ListDirectoryParams(dir_path=".")
    result = file_specialist._list_directory(params)
    
    assert "file1.txt" in result
    assert "subdir" in result
    
    params_subdir = ListDirectoryParams(dir_path="subdir")
    result_subdir = file_specialist._list_directory(params_subdir)
    assert "file2.txt" in result_subdir

def test_list_directory_non_existent(file_specialist):
    """Tests listing a directory that does not exist."""
    params = ListDirectoryParams(dir_path="non_existent_dir")
    result = file_specialist._list_directory(params)
    assert "Error listing directory" in result

def test_list_directory_empty(file_specialist, tmp_path):
    """Tests listing an empty directory."""
    workspace = tmp_path / "test_workspace"
    (workspace / "empty_dir").mkdir()
    params = ListDirectoryParams(dir_path="empty_dir")
    result = file_specialist._list_directory(params)
    assert "Directory is empty" in result

def test_execute_logic_reads_file(file_specialist, tmp_path):
    """Tests the full logic execution for a read_file operation."""
    # Arrange
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    test_file.write_text("file content")

    # Mock the LLM response
    mock_json_response = {
        "tool_name": "read_file",
        "tool_input": {"file_path": "test.txt"}
    }
    file_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}

    initial_state = {"messages": [HumanMessage(content="Read test.txt")]}

    # Act
    result_state = file_specialist._execute_logic(initial_state)

    # Assert
    file_specialist.llm_adapter.invoke.assert_called_once()
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "FileSpecialist action 'read_file' completed" in result_state["messages"][0].content
    assert "text_to_process" in result_state
    assert result_state["text_to_process"] == "file content"
    assert result_state.get("suggested_next_specialist") == "text_analysis_specialist"

def test_execute_logic_writes_file_safety_on(file_specialist, tmp_path):
    """Tests the full logic for a write_file operation when safety is ON."""
    # Arrange
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    file_specialist.is_safety_on = True # Explicitly set for test clarity
    mock_json_response = {
        "tool_name": "write_file",
        "tool_input": {"file_path": "test.txt", "content": "written content"}
    }
    file_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}
    initial_state = {"messages": [HumanMessage(content="Write to test.txt")]}

    # Act
    result_state = file_specialist._execute_logic(initial_state)

    # Assert
    # Assert that the file was NOT created.
    assert not test_file.exists()
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "DRY RUN" in result_state["messages"][0].content
    assert "text_to_process" not in result_state # Write ops shouldn't populate this

def test_execute_logic_writes_file_safety_off(file_specialist, tmp_path):
    """Tests the full logic for a write_file operation when safety is OFF."""
    # Arrange
    workspace = tmp_path / "test_workspace"
    test_file = workspace / "test.txt"
    file_specialist.is_safety_on = False # Explicitly disable safety for this test
    mock_json_response = {
        "tool_name": "write_file",
        "tool_input": {"file_path": "test.txt", "content": "written content"}
    }
    file_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}
    initial_state = {"messages": [HumanMessage(content="Write to test.txt")]}
    # Act
    result_state = file_specialist._execute_logic(initial_state)
    # Assert
    assert test_file.exists()
    assert test_file.read_text() == "written content"
    assert "Successfully wrote" in result_state["messages"][0].content

def test_execute_logic_handles_llm_failure(file_specialist):
    """Tests that the specialist handles when the LLM adapter itself fails."""
    # Arrange
    file_specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API Error")
    initial_state = {"messages": [HumanMessage(content="some request")]}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API Error"):
        file_specialist._execute_logic(initial_state)

def test_execute_logic_handles_malformed_tool_input(file_specialist):
    """Tests handling of LLM responses where tool_input is malformed."""
    # Arrange
    mock_json_response = {
        "tool_name": "read_file",
        "tool_input": {"wrong_param": "test.txt"} # Missing 'file_path'
    }
    file_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}
    initial_state = {"messages": [HumanMessage(content="Read the file")]}
    # Act
    result_state = file_specialist._execute_logic(initial_state)
    # Assert
    assert "Failed to validate tool input" in result_state["messages"][0].content

def test_execute_logic_handles_llm_no_json(file_specialist):
    """Tests that the specialist handles when the LLM fails to return a valid Pydantic object."""
    # Arrange
    file_specialist.llm_adapter.invoke.return_value = {"json_response": None}
    initial_state = {"messages": [HumanMessage(content="gibberish request")]}

    # Act
    result_state = file_specialist._execute_logic(initial_state)

    # Assert
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "did not return a valid, structured tool call" in result_state["messages"][0].content
    assert "text_to_process" not in result_state

def test_execute_logic_lists_directory(file_specialist, tmp_path):
    """Tests the full logic execution for a list_directory operation."""
    # Arrange
    workspace = tmp_path / "test_workspace"
    (workspace / "file1.txt").touch()
    (workspace / "subdir").mkdir()

    mock_json_response = {
        "tool_name": "list_directory",
        "tool_input": {"dir_path": "."}
    }
    file_specialist.llm_adapter.invoke.return_value = {"json_response": mock_json_response}
    initial_state = {"messages": [HumanMessage(content="List files")]}

    # Act
    result_state = file_specialist._execute_logic(initial_state)

    # Assert
    assert "FileSpecialist action 'list_directory' completed" in result_state["messages"][0].content
    assert "file1.txt" in result_state["text_to_process"]
    assert "subdir" in result_state["text_to_process"]
