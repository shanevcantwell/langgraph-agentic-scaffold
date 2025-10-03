import logging
import os
import shutil
from typing import Dict, Any, Union

from langchain_core.messages import ToolMessage

from .base import BaseSpecialist
from .schemas import (
    CreateDirectoryParams,
    WriteFileParams,
    CreateZipFromDirectoryParams,
)
from app.src.utils.errors import SpecialistError

logger = logging.getLogger(__name__)

class FileSpecialist(BaseSpecialist):
    """
    A procedural specialist that provides composable file system tools.
    This specialist executes tool calls for directory creation, file writing, and zipping.
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # Configuration for the root directory can be added here if needed

    def _create_directory(self, path: str) -> str:
        """Creates a directory and any missing parent directories."""
        try:
            os.makedirs(path, exist_ok=True)
            msg = f"Successfully created directory: {path}"
            logger.info(msg)
            return msg
        except Exception as e:
            raise SpecialistError(f"Error creating directory at {path}: {e}")

    def _write_file(self, path: str, content: Union[str, bytes]) -> str:
        """Writes content to a file, creating parent directories if necessary."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            mode = 'wb' if isinstance(content, bytes) else 'w'
            with open(path, mode) as f:
                f.write(content)
            msg = f"Successfully wrote file: {path}"
            logger.info(msg)
            return msg
        except Exception as e:
            raise SpecialistError(f"Error writing file at {path}: {e}")

    def _create_zip_from_directory(self, source_path: str, destination_path: str) -> str:
        """Creates a zip archive from a source directory."""
        try:
            # shutil.make_archive will create the parent directory for the destination if it doesn't exist
            archive_path_without_ext = destination_path.removesuffix('.zip')
            shutil.make_archive(archive_path_without_ext, 'zip', source_path)
            msg = f"Successfully created zip archive from '{source_path}' to '{destination_path}'"
            logger.info(msg)
            return msg
        except Exception as e:
            raise SpecialistError(f"Error creating zip from '{source_path}': {e}")

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Procedural tool dispatcher for file operations."""
        last_message = state["messages"][-1]
        if not isinstance(last_message, ToolMessage):
            # This specialist should only be called with a ToolMessage
            # In a future iteration, we might return an error message
            return {}

        tool_call = last_message
        tool_name = tool_call.name
        tool_args = tool_call.additional_kwargs.get('parsed_args', {})

        status_message = ""
        try:
            if tool_name == WriteFileParams.__name__:
                params = WriteFileParams(**tool_args)
                status_message = self._write_file(params.path, params.content)
            elif tool_name == CreateZipFromDirectoryParams.__name__:
                params = CreateZipFromDirectoryParams(**tool_args)
                status_message = self._create_zip_from_directory(params.source_path, params.destination_path)
            else:
                status_message = f"Unknown tool '{tool_name}' called on FileSpecialist."
                logger.warning(status_message)

        except SpecialistError as e:
            status_message = str(e)
            logger.error(f"FileSpecialist Error: {status_message}")
        except Exception as e:
            status_message = f"An unexpected error occurred in {tool_name}: {e}"
            logger.error(status_message, exc_info=True)

        # Return a new ToolMessage with the result of the operation
        response_message = ToolMessage(
            content=status_message,
            tool_call_id=tool_call.tool_call_id,
            name=self.specialist_name
        )

        return {
            "messages": [response_message],
            # Add a user-facing summary of the action to the scratchpad.
            "scratchpad": {"user_response_snippets": [status_message]}
        }