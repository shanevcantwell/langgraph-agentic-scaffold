# app/tests/specialists/schemas/test_file_ops_schemas.py
import pytest
from pydantic import ValidationError
from app.src.specialists.schemas import ReadFileParams, WriteFileParams, ListDirectoryParams

def test_read_file_params():
    """Tests that ReadFileParams inherits file_path correctly."""
    params = ReadFileParams(file_path="/path/to/file.txt")
    assert params.file_path == "/path/to/file.txt"

def test_write_file_params():
    """Tests that WriteFileParams has both inherited and its own fields."""
    params = WriteFileParams(file_path="/path/to/file.txt", content="Hello")
    assert params.file_path == "/path/to/file.txt"
    assert params.content == "Hello"

def test_write_file_params_missing_content():
    """Tests validation error when a required field is missing."""
    with pytest.raises(ValidationError):
        WriteFileParams(file_path="/path/to/file.txt")

def test_list_directory_params_default():
    """Tests that ListDirectoryParams uses its default value correctly."""
    params = ListDirectoryParams()
    assert params.dir_path == "."
