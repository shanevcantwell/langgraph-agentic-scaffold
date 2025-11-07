import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Any, Union, List

from .base import BaseSpecialist
from app.src.utils.errors import SpecialistError

logger = logging.getLogger(__name__)


class FileSpecialist(BaseSpecialist):
    """
    A procedural specialist that provides file system operations via MCP.

    This specialist exposes functions for directory creation, file reading/writing,
    and archive operations. All operations are scoped to a root directory for safety.

    MCP Services Exposed:
    - file_exists(path: str) -> bool
    - read_file(path: str) -> str
    - write_file(path: str, content: str) -> str
    - list_files(path: str) -> List[str]
    - create_directory(path: str) -> str
    - create_zip(source_path: str, destination_path: str) -> str
    """

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)

        # Get root directory from config, default to ./workspace
        self.root_dir = Path(specialist_config.get("root_dir", "./workspace"))

        # Ensure root directory is absolute and exists
        if not self.root_dir.is_absolute():
            self.root_dir = Path.cwd() / self.root_dir

        self.root_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileSpecialist initialized with root_dir: {self.root_dir}")

    def _validate_path(self, path: str) -> Path:
        """
        Validates and normalizes a path to ensure it's within root_dir.

        Args:
            path: Relative or absolute path to validate

        Returns:
            Absolute Path object within root_dir

        Raises:
            SpecialistError: If path escapes root_dir
        """
        # Convert to Path object
        target = Path(path)

        # If relative, make it relative to root_dir
        if not target.is_absolute():
            target = self.root_dir / target

        # Resolve to absolute path (handles .. and symlinks)
        try:
            target = target.resolve()
        except (OSError, RuntimeError) as e:
            raise SpecialistError(f"Invalid path '{path}': {e}")

        # Ensure target is within root_dir
        try:
            target.relative_to(self.root_dir)
        except ValueError:
            raise SpecialistError(
                f"Path '{path}' escapes root directory '{self.root_dir}'. "
                f"All file operations must be within the workspace."
            )

        return target

    # ==========================================================================
    # MCP Service Functions (Exposed via register_mcp_services)
    # ==========================================================================

    def file_exists(self, path: str) -> bool:
        """
        Check if a file or directory exists.

        Args:
            path: Path to check (relative to root_dir or absolute)

        Returns:
            True if file/directory exists, False otherwise
        """
        try:
            validated_path = self._validate_path(path)
            exists = validated_path.exists()
            logger.debug(f"file_exists({path}): {exists}")
            return exists
        except SpecialistError as e:
            logger.error(f"file_exists error: {e}")
            raise

    def read_file(self, path: str) -> str:
        """
        Read contents of a text file.

        Args:
            path: Path to file (relative to root_dir or absolute)

        Returns:
            File contents as string

        Raises:
            SpecialistError: If file doesn't exist or cannot be read
        """
        try:
            validated_path = self._validate_path(path)

            if not validated_path.exists():
                raise SpecialistError(f"File not found: {path}")

            if not validated_path.is_file():
                raise SpecialistError(f"Path is not a file: {path}")

            content = validated_path.read_text()
            logger.info(f"Successfully read file: {path} ({len(content)} chars)")
            return content

        except SpecialistError:
            raise
        except Exception as e:
            raise SpecialistError(f"Error reading file '{path}': {e}")

    def write_file(self, path: str, content: str) -> str:
        """
        Write content to a file, creating parent directories if necessary.

        Args:
            path: Path to file (relative to root_dir or absolute)
            content: Content to write (string)

        Returns:
            Success message

        Raises:
            SpecialistError: If write fails
        """
        try:
            validated_path = self._validate_path(path)

            # Create parent directories if needed
            validated_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            validated_path.write_text(content)

            msg = f"Successfully wrote file: {path} ({len(content)} chars)"
            logger.info(msg)
            return msg

        except SpecialistError:
            raise
        except Exception as e:
            raise SpecialistError(f"Error writing file '{path}': {e}")

    def list_files(self, path: str = ".") -> List[str]:
        """
        List files and directories at the given path.

        Args:
            path: Directory path (relative to root_dir or absolute). Defaults to root.

        Returns:
            List of file/directory names (not full paths)

        Raises:
            SpecialistError: If path doesn't exist or isn't a directory
        """
        try:
            validated_path = self._validate_path(path)

            if not validated_path.exists():
                raise SpecialistError(f"Path not found: {path}")

            if not validated_path.is_dir():
                raise SpecialistError(f"Path is not a directory: {path}")

            # List directory contents (names only, not full paths)
            items = [item.name for item in validated_path.iterdir()]
            items.sort()  # Consistent ordering

            logger.info(f"Listed {len(items)} items in: {path}")
            return items

        except SpecialistError:
            raise
        except Exception as e:
            raise SpecialistError(f"Error listing directory '{path}': {e}")

    def create_directory(self, path: str) -> str:
        """
        Create a directory and any missing parent directories.

        Args:
            path: Directory path (relative to root_dir or absolute)

        Returns:
            Success message

        Raises:
            SpecialistError: If creation fails
        """
        try:
            validated_path = self._validate_path(path)
            validated_path.mkdir(parents=True, exist_ok=True)

            msg = f"Successfully created directory: {path}"
            logger.info(msg)
            return msg

        except SpecialistError:
            raise
        except Exception as e:
            raise SpecialistError(f"Error creating directory '{path}': {e}")

    def create_zip(self, source_path: str, destination_path: str) -> str:
        """
        Create a zip archive from a source directory.

        Args:
            source_path: Source directory to zip (relative to root_dir or absolute)
            destination_path: Destination zip file path (relative to root_dir or absolute)

        Returns:
            Success message

        Raises:
            SpecialistError: If zip creation fails
        """
        try:
            validated_source = self._validate_path(source_path)
            validated_dest = self._validate_path(destination_path)

            if not validated_source.exists():
                raise SpecialistError(f"Source directory not found: {source_path}")

            if not validated_source.is_dir():
                raise SpecialistError(f"Source path is not a directory: {source_path}")

            # Remove .zip extension if present (shutil.make_archive adds it)
            archive_base = str(validated_dest).removesuffix('.zip')

            # Create archive
            shutil.make_archive(archive_base, 'zip', str(validated_source))

            msg = f"Successfully created zip archive: {destination_path}"
            logger.info(msg)
            return msg

        except SpecialistError:
            raise
        except Exception as e:
            raise SpecialistError(f"Error creating zip from '{source_path}': {e}")

    # ==========================================================================
    # MCP Registration
    # ==========================================================================

    def register_mcp_services(self, registry):
        """
        Register FileSpecialist's functions as MCP services.

        This exposes all file operations to other specialists via McpClient.
        """
        registry.register_service(self.specialist_name, {
            "file_exists": self.file_exists,
            "read_file": self.read_file,
            "write_file": self.write_file,
            "list_files": self.list_files,
            "create_directory": self.create_directory,
            "create_zip": self.create_zip,
        })
        logger.info(f"Registered 6 MCP services for {self.specialist_name}")

    # ==========================================================================
    # Graph Execution (No-op for MCP-only mode)
    # ==========================================================================

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        FileSpecialist operates exclusively via MCP.

        This specialist is never invoked directly through graph execution.
        Other specialists call its functions via mcp_client.call().

        Returns:
            Empty dict (no state updates)
        """
        logger.warning(
            f"{self.specialist_name}._execute_logic() called, but this specialist "
            f"operates exclusively via MCP. Use mcp_client.call() instead."
        )
        return {}
