# app/src/specialists/schemas/_file_ops.py
from typing import Union
from pydantic import BaseModel, Field

class CreateDirectoryParams(BaseModel):
    """Parameters for creating a directory."""
    path: str = Field(..., description="The path of the directory to create.", min_length=1)

class WriteFileParams(BaseModel):
    """Parameters for writing content to a file."""
    path: str = Field(..., description="The full path (including filename) where the file will be written.", min_length=1)
    content: Union[str, bytes] = Field(..., description="The content to write.")

class CreateZipFromDirectoryParams(BaseModel):
    """Parameters for creating a zip archive from a directory."""
    source_path: str = Field(..., description="The path to the directory to be compressed.", min_length=1)
    destination_path: str = Field(..., description="The full path (including filename) for the output .zip file.", min_length=1)