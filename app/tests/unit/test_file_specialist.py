"""
Unit tests for FileSpecialist - MCP-only mode.

Tests validate MCP service functions, path validation security,
service registration, and no-op execute_logic behavior.
"""

import pytest
import shutil
from pathlib import Path
from unittest.mock import Mock

from app.src.specialists.file_specialist import FileSpecialist
from app.src.utils.errors import SpecialistError


@pytest.fixture
def file_specialist_instance(initialized_specialist_factory, tmp_path):
    """
    Provides a clean FileSpecialist instance for each test.

    Uses tmp_path as root_dir to isolate file operations.
    """
    # Override config to use tmp_path as root_dir
    specialist = initialized_specialist_factory("FileSpecialist", "file_specialist")
    specialist.root_dir = tmp_path
    return specialist


# ==============================================================================
# Group 1: MCP Service Function Tests
# ==============================================================================

class TestFileExists:
    """Test suite for file_exists MCP service function."""

    def test_file_exists_returns_true_for_existing_file(self, file_specialist_instance, tmp_path):
        """Test that file_exists returns True for existing file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        result = file_specialist_instance.file_exists("test.txt")

        assert result is True

    def test_file_exists_returns_true_for_existing_directory(self, file_specialist_instance, tmp_path):
        """Test that file_exists returns True for existing directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        result = file_specialist_instance.file_exists("test_dir")

        assert result is True

    def test_file_exists_returns_false_for_nonexistent_path(self, file_specialist_instance):
        """Test that file_exists returns False for nonexistent path."""
        result = file_specialist_instance.file_exists("nonexistent.txt")

        assert result is False

    def test_file_exists_rejects_path_escape_attempt(self, file_specialist_instance):
        """Test that file_exists rejects directory traversal attempts."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.file_exists("../../etc/passwd")

        assert "escapes root directory" in str(exc_info.value)


class TestReadFile:
    """Test suite for read_file MCP service function."""

    def test_read_file_returns_content(self, file_specialist_instance, tmp_path):
        """Test that read_file returns file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = file_specialist_instance.read_file("test.txt")

        assert result == "hello world"

    def test_read_file_handles_multiline_content(self, file_specialist_instance, tmp_path):
        """Test that read_file preserves newlines."""
        test_file = tmp_path / "multiline.txt"
        content = "line1\nline2\nline3"
        test_file.write_text(content)

        result = file_specialist_instance.read_file("multiline.txt")

        assert result == content

    def test_read_file_raises_on_nonexistent_file(self, file_specialist_instance):
        """Test that read_file raises SpecialistError for nonexistent file."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.read_file("nonexistent.txt")

        assert "File not found" in str(exc_info.value)

    def test_read_file_raises_on_directory(self, file_specialist_instance, tmp_path):
        """Test that read_file raises SpecialistError when path is directory."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.read_file("test_dir")

        assert "not a file" in str(exc_info.value)

    def test_read_file_rejects_path_escape_attempt(self, file_specialist_instance):
        """Test that read_file rejects directory traversal attempts."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.read_file("../../etc/passwd")

        assert "escapes root directory" in str(exc_info.value)


class TestWriteFile:
    """Test suite for write_file MCP service function."""

    def test_write_file_creates_new_file(self, file_specialist_instance, tmp_path):
        """Test that write_file creates new file with content."""
        result = file_specialist_instance.write_file("new.txt", "hello")

        assert (tmp_path / "new.txt").read_text() == "hello"
        assert "Successfully wrote file" in result

    def test_write_file_overwrites_existing_file(self, file_specialist_instance, tmp_path):
        """Test that write_file overwrites existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("old content")

        file_specialist_instance.write_file("existing.txt", "new content")

        assert test_file.read_text() == "new content"

    def test_write_file_creates_parent_directories(self, file_specialist_instance, tmp_path):
        """Test that write_file creates missing parent directories."""
        file_specialist_instance.write_file("subdir/nested/file.txt", "content")

        assert (tmp_path / "subdir" / "nested" / "file.txt").read_text() == "content"

    def test_write_file_handles_empty_content(self, file_specialist_instance, tmp_path):
        """Test that write_file can write empty file."""
        file_specialist_instance.write_file("empty.txt", "")

        assert (tmp_path / "empty.txt").read_text() == ""

    def test_write_file_rejects_path_escape_attempt(self, file_specialist_instance):
        """Test that write_file rejects directory traversal attempts."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.write_file("../../etc/malicious.txt", "bad")

        assert "escapes root directory" in str(exc_info.value)


class TestListFiles:
    """Test suite for list_files MCP service function."""

    def test_list_files_returns_directory_contents(self, file_specialist_instance, tmp_path):
        """Test that list_files returns all files and directories."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.txt").touch()
        (tmp_path / "subdir").mkdir()

        result = file_specialist_instance.list_files(".")

        assert sorted(result) == ["file1.txt", "file2.txt", "subdir"]

    def test_list_files_returns_empty_for_empty_directory(self, file_specialist_instance):
        """Test that list_files returns empty list for empty directory."""
        result = file_specialist_instance.list_files(".")

        assert result == []

    def test_list_files_lists_subdirectory(self, file_specialist_instance, tmp_path):
        """Test that list_files can list subdirectory contents."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").touch()

        result = file_specialist_instance.list_files("subdir")

        assert result == ["nested.txt"]

    def test_list_files_raises_on_nonexistent_directory(self, file_specialist_instance):
        """Test that list_files raises SpecialistError for nonexistent directory."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.list_files("nonexistent")

        assert "not found" in str(exc_info.value)

    def test_list_files_raises_on_file_path(self, file_specialist_instance, tmp_path):
        """Test that list_files raises SpecialistError when path is file."""
        test_file = tmp_path / "file.txt"
        test_file.touch()

        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.list_files("file.txt")

        assert "not a directory" in str(exc_info.value)

    def test_list_files_rejects_path_escape_attempt(self, file_specialist_instance):
        """Test that list_files rejects directory traversal attempts."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.list_files("../../etc")

        assert "escapes root directory" in str(exc_info.value)


class TestCreateDirectory:
    """Test suite for create_directory MCP service function."""

    def test_create_directory_creates_new_directory(self, file_specialist_instance, tmp_path):
        """Test that create_directory creates new directory."""
        result = file_specialist_instance.create_directory("new_dir")

        assert (tmp_path / "new_dir").is_dir()
        assert "Successfully created directory" in result

    def test_create_directory_creates_nested_directories(self, file_specialist_instance, tmp_path):
        """Test that create_directory creates missing parent directories."""
        file_specialist_instance.create_directory("parent/child/grandchild")

        assert (tmp_path / "parent" / "child" / "grandchild").is_dir()

    def test_create_directory_succeeds_if_already_exists(self, file_specialist_instance, tmp_path):
        """Test that create_directory is idempotent (succeeds if dir exists)."""
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = file_specialist_instance.create_directory("existing")

        assert "Successfully created directory" in result

    def test_create_directory_rejects_path_escape_attempt(self, file_specialist_instance):
        """Test that create_directory rejects directory traversal attempts."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_directory("../../tmp/malicious")

        assert "escapes root directory" in str(exc_info.value)


class TestCreateZip:
    """Test suite for create_zip MCP service function."""

    def test_create_zip_creates_archive(self, file_specialist_instance, tmp_path):
        """Test that create_zip creates zip archive from directory."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")

        result = file_specialist_instance.create_zip("source", "archive.zip")

        assert (tmp_path / "archive.zip").is_file()
        assert "Successfully created zip archive" in result

    def test_create_zip_preserves_directory_structure(self, file_specialist_instance, tmp_path):
        """Test that create_zip preserves nested directory structure."""
        source_dir = tmp_path / "source"
        nested = source_dir / "nested"
        nested.mkdir(parents=True)
        (nested / "nested_file.txt").write_text("nested content")

        file_specialist_instance.create_zip("source", "archive.zip")

        # Unpack and verify
        unpack_dir = tmp_path / "unpacked"
        shutil.unpack_archive(str(tmp_path / "archive.zip"), str(unpack_dir))
        assert (unpack_dir / "nested" / "nested_file.txt").read_text() == "nested content"

    def test_create_zip_handles_zip_extension_in_dest(self, file_specialist_instance, tmp_path):
        """Test that create_zip handles .zip extension correctly."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").touch()

        # Both should work (with and without .zip extension)
        file_specialist_instance.create_zip("source", "archive1.zip")
        file_specialist_instance.create_zip("source", "archive2")

        assert (tmp_path / "archive1.zip").is_file()
        assert (tmp_path / "archive2.zip").is_file()

    def test_create_zip_raises_on_nonexistent_source(self, file_specialist_instance):
        """Test that create_zip raises SpecialistError for nonexistent source."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_zip("nonexistent", "archive.zip")

        assert "not found" in str(exc_info.value)

    def test_create_zip_raises_on_file_source(self, file_specialist_instance, tmp_path):
        """Test that create_zip raises SpecialistError when source is file."""
        test_file = tmp_path / "file.txt"
        test_file.touch()

        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_zip("file.txt", "archive.zip")

        assert "not a directory" in str(exc_info.value)

    def test_create_zip_rejects_source_path_escape(self, file_specialist_instance):
        """Test that create_zip rejects directory traversal in source path."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_zip("../../etc", "archive.zip")

        assert "escapes root directory" in str(exc_info.value)

    def test_create_zip_rejects_dest_path_escape(self, file_specialist_instance, tmp_path):
        """Test that create_zip rejects directory traversal in dest path."""
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_zip("source", "../../tmp/malicious.zip")

        assert "escapes root directory" in str(exc_info.value)


class TestCreateManifest:
    """Test suite for create_manifest MCP service function."""

    def test_create_manifest_creates_valid_json(self, file_specialist_instance, tmp_path):
        """Test that create_manifest creates a valid JSON file."""
        manifest_data = {
            "run_id": "test-run-123",
            "final_response_generated": True,
            "termination_reason": "success",
            "routing_history": ["node1", "node2"],
            "artifacts": []
        }
        
        result = file_specialist_instance.create_manifest("manifest.json", manifest_data)
        
        manifest_file = tmp_path / "manifest.json"
        assert manifest_file.exists()
        assert "Successfully wrote file" in result
        
        # Verify content
        import json
        content = json.loads(manifest_file.read_text())
        assert content["run_id"] == "test-run-123"
        assert content["timestamp"] is not None # Should be auto-generated

    def test_create_manifest_validates_schema(self, file_specialist_instance):
        """Test that create_manifest raises error for invalid data."""
        invalid_data = {
            "run_id": "test-run-123",
            # Missing required fields like final_response_generated
        }
        
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_manifest("manifest.json", invalid_data)
            
        assert "Error creating manifest" in str(exc_info.value)

    def test_create_manifest_rejects_path_escape(self, file_specialist_instance):
        """Test that create_manifest rejects directory traversal."""
        data = {
            "run_id": "test",
            "final_response_generated": True,
            "termination_reason": "success"
        }
        
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance.create_manifest("../../manifest.json", data)
            
        assert "escapes root directory" in str(exc_info.value)


# ==============================================================================
# Group 2: Path Validation Tests
# ==============================================================================

class TestPathValidation:
    """Test suite for _validate_path security enforcement."""

    def test_validate_path_accepts_relative_paths(self, file_specialist_instance, tmp_path):
        """Test that relative paths within root_dir are accepted."""
        validated = file_specialist_instance._validate_path("subdir/file.txt")

        assert validated == tmp_path / "subdir" / "file.txt"

    def test_validate_path_accepts_current_directory(self, file_specialist_instance, tmp_path):
        """Test that '.' resolves to root_dir."""
        validated = file_specialist_instance._validate_path(".")

        assert validated == tmp_path

    def test_validate_path_rejects_parent_directory_traversal(self, file_specialist_instance):
        """Test that .. traversal escaping root_dir is rejected."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance._validate_path("../../../etc/passwd")

        assert "escapes root directory" in str(exc_info.value)

    def test_validate_path_rejects_absolute_path_outside_root(self, file_specialist_instance):
        """Test that absolute paths outside root_dir are rejected."""
        with pytest.raises(SpecialistError) as exc_info:
            file_specialist_instance._validate_path("/etc/passwd")

        assert "escapes root directory" in str(exc_info.value)

    def test_validate_path_accepts_absolute_path_inside_root(self, file_specialist_instance, tmp_path):
        """Test that absolute paths within root_dir are accepted."""
        subdir = tmp_path / "subdir"
        validated = file_specialist_instance._validate_path(str(subdir))

        assert validated == subdir


# ==============================================================================
# Group 3: MCP Integration Tests
# ==============================================================================

class TestMcpIntegration:
    """Test suite for MCP service registration."""

    def test_register_mcp_services_exposes_all_functions(self, file_specialist_instance):
        """Test that register_mcp_services exposes all 6 functions."""
        mock_registry = Mock()

        file_specialist_instance.register_mcp_services(mock_registry)

        # Verify register_service was called
        mock_registry.register_service.assert_called_once()

        # Get the registered functions
        call_args = mock_registry.register_service.call_args
        service_name = call_args[0][0]
        functions = call_args[0][1]

        assert service_name == file_specialist_instance.specialist_name
        assert len(functions) == 10
        assert "file_exists" in functions
        assert "read_file" in functions
        assert "write_file" in functions
        assert "append_to_file" in functions
        assert "rename_file" in functions
        assert "delete_file" in functions
        assert "list_files" in functions
        assert "create_directory" in functions
        assert "create_zip" in functions
        assert "create_manifest" in functions


# ==============================================================================
# Group 4: Execute Logic Tests (No-op Behavior)
# ==============================================================================

class TestExecuteLogic:
    """Test suite for _execute_logic no-op behavior."""

    def test_execute_logic_returns_empty_dict(self, file_specialist_instance):
        """Test that _execute_logic returns empty dict (no-op)."""
        state = {"messages": [], "scratchpad": {}}

        result = file_specialist_instance._execute_logic(state)

        assert result == {}

    def test_execute_logic_logs_warning(self, file_specialist_instance, caplog):
        """Test that _execute_logic logs warning about MCP-only mode."""
        state = {}

        file_specialist_instance._execute_logic(state)

        assert "operates exclusively via MCP" in caplog.text
