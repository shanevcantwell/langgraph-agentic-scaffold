import pytest
from pathlib import Path
from src.specialists.file_specialist import FileSpecialist

# Architectural Note: The 'tmp_path' fixture is provided by pytest.
# It creates a unique temporary directory for each test function, ensuring that
# tests are isolated and do not interfere with each other or leave artifacts
# on the filesystem. This is the standard best practice for testing file I/O.

@pytest.fixture
def file_specialist(tmp_path):
    """Fixture to create a FileSpecialist instance rooted in a temporary directory."""
    return FileSpecialist(root_dir=str(tmp_path))

def test_write_file(file_specialist, tmp_path):
    """Tests that the write_file tool correctly creates a file with the specified content."""
    file_path = "test_document.txt"
    content = "This is a test."
    
    result = file_specialist.write_file(file_path, content)
    
    full_path = tmp_path / file_path
    assert full_path.exists()
    assert full_path.read_text() == content
    assert result == f"File '{file_path}' has been written successfully."

def test_read_file(file_specialist, tmp_path):
    """Tests that the read_file tool correctly reads the content of an existing file."""
    file_path = "test_document.txt"
    content = "Hello from the test."
    (tmp_path / file_path).write_text(content)
    
    read_content = file_specialist.read_file(file_path)
    
    assert read_content == content

def test_read_file_not_found(file_specialist):
    """Tests that the read_file tool returns an informative error for a non-existent file."""
    non_existent_file = "this_file_does_not_exist.txt"
    
    result = file_specialist.read_file(non_existent_file)
    
    assert "Error: File not found at" in result
    assert non_existent_file in result

def test_list_files(file_specialist, tmp_path):
    """Tests that the list_files tool correctly lists files and directories."""
    # Create some structure
    (tmp_path / "file1.txt").touch()
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "subfile.txt").touch()
    
    # Test listing the root
    root_listing = file_specialist.list_files(".")
    assert "file1.txt" in root_listing
    assert "subdir/" in root_listing
    
    # Test listing the subdirectory
    subdir_listing = file_specialist.list_files("subdir")
    assert "subfile.txt" in subdir_listing
