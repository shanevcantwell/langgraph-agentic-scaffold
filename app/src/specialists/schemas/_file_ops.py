# app/src/specialists/schemas/_file_ops.py
from pydantic import BaseModel, Field

class BaseFileParams(BaseModel):
    """A base model for operations that target a file path."""
    file_path: str = Field(..., description="The relative path to the file.", min_length=1)

class ReadFileParams(BaseFileParams):
    """Parameters for reading the contents of a file."""
    pass

class WriteFileParams(BaseFileParams):
    """Parameters for writing content to a file."""
    content: str = Field(..., description="The content to write into the file.")

class ListDirectoryParams(BaseModel):
    """Parameters for listing the contents of a directory."""
    dir_path: str = Field(
        default=".",
        description="The relative path to the directory to be listed.",
        min_length=1
    )