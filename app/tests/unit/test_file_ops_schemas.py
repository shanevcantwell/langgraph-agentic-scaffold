# Audited on Sept 23, 2025
# app/tests/specialists/schemas/test_file_ops_schemas.py
import pytest
from pydantic import ValidationError
from app.src.specialists.schemas._file_ops import ReadFileParams, WriteFileParams, ListDirectoryParams

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

def test_list_directory_params_explicit_path():
    """Tests that ListDirectoryParams accepts an explicit path."""
    params = ListDirectoryParams(dir_path="some/dir")
    assert params.dir_path == "some/dir"

@pytest.mark.parametrize("param_class, field", [
    (ReadFileParams, "file_path"),
    (WriteFileParams, "file_path"),
    (ListDirectoryParams, "dir_path"),
])
def test_path_params_reject_empty_string(param_class, field):
    """
    Tests that path parameters do not allow empty strings.
    This assumes the Pydantic models have validation like `min_length=1`.
    """
    with pytest.raises(ValidationError):
        # For WriteFileParams, content is also required for valid instantiation
        if param_class == WriteFileParams:
            param_class(**{field: "", "content": "some content"})
        else:
            param_class(**{field: ""})

def test_write_file_params_allows_empty_content():
    """Tests that writing an empty string as content is valid."""
    params = WriteFileParams(file_path="/path/to/file.txt", content="")
    assert params.content == ""
