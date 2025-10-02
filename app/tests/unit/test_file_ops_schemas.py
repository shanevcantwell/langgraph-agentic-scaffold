# app/tests/unit/test_file_ops_schemas.py
import pytest
from pydantic import ValidationError
from app.src.specialists.schemas._file_ops import (
    CreateDirectoryParams,
    WriteFileParams,
    CreateZipFromDirectoryParams,
)

def test_create_directory_params():
    """Tests valid CreateDirectoryParams."""
    params = CreateDirectoryParams(path="/some/new/dir")
    assert params.path == "/some/new/dir"

def test_write_file_params():
    """Tests valid WriteFileParams with string and bytes content."""
    # Test with string content
    params_str = WriteFileParams(path="/path/to/file.txt", content="Hello, world!")
    assert params_str.path == "/path/to/file.txt"
    assert params_str.content == "Hello, world!"

    # Test with bytes content
    params_bytes = WriteFileParams(path="/path/to/binary.dat", content=b"\x01\x02\x03")
    assert params_bytes.path == "/path/to/binary.dat"
    assert params_bytes.content == b"\x01\x02\x03"

def test_create_zip_from_directory_params():
    """Tests valid CreateZipFromDirectoryParams."""
    params = CreateZipFromDirectoryParams(source_path="/path/to/source", destination_path="/path/to/archive.zip")
    assert params.source_path == "/path/to/source"
    assert params.destination_path == "/path/to/archive.zip"

@pytest.mark.parametrize("param_class, data", [
    (CreateDirectoryParams, {"path": ""}),
    (WriteFileParams, {"path": "/some/path", "content": None}), # Content is required
    (WriteFileParams, {"path": "", "content": "some content"}),
    (CreateZipFromDirectoryParams, {"source_path": "", "destination_path": "/dest"}),
    (CreateZipFromDirectoryParams, {"source_path": "/src", "destination_path": ""}),
])
def test_invalid_params_raise_validation_error(param_class, data):
    """Tests that Pydantic models raise ValidationError for invalid input."""
    with pytest.raises(ValidationError):
        param_class(**data)

def test_write_file_params_allows_empty_content():
    """Tests that writing an empty string or empty bytes as content is valid."""
    params_str = WriteFileParams(path="/path/to/file.txt", content="")
    assert params_str.content == ""

    params_bytes = WriteFileParams(path="/path/to/file.txt", content=b"")
    assert params_bytes.content == b""