"""
File tree helpers for integration tests.

Simple, composable functions for creating test folder structures.
Each function returns the absolute path to what it created.
"""
import shutil
import uuid
from pathlib import Path
from typing import Optional


def folder_of_empty_files(
    folder_name: str,
    file_pattern: str,
    num_files: int,
    workspace_root: str = "workspace"
) -> Path:
    """
    Create a folder with N empty files matching a pattern.

    Args:
        folder_name: Name of folder to create (can include path segments)
        file_pattern: Pattern with {n} placeholder, e.g. "file_{n}.txt"
        num_files: Number of files to create
        workspace_root: Base workspace directory

    Returns:
        Absolute path to the created folder

    Example:
        path = folder_of_empty_files("test_abc/to_sort", "doc_{n}.md", 5)
        # Creates: workspace/test_abc/to_sort/doc_1.md through doc_5.md
    """
    folder_path = Path(workspace_root) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    for i in range(1, num_files + 1):
        filename = file_pattern.format(n=i)
        (folder_path / filename).touch()

    return folder_path.resolve()


def folder_of_files_with_content(
    folder_name: str,
    files: dict,
    workspace_root: str = "workspace"
) -> Path:
    """
    Create a folder with files containing specific content.

    Args:
        folder_name: Name of folder to create
        files: Dict of filename -> content
        workspace_root: Base workspace directory

    Returns:
        Absolute path to the created folder

    Example:
        path = folder_of_files_with_content("test_abc/ADRs", {
            "ADR-001.md": "# ADR-001\nStatus: Accepted",
            "ADR-002.md": "# ADR-002\nStatus: Draft",
        })
    """
    folder_path = Path(workspace_root) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)

    for filename, content in files.items():
        (folder_path / filename).write_text(content)

    return folder_path.resolve()


def empty_folders(
    parent: str,
    folder_names: list,
    workspace_root: str = "workspace"
) -> list:
    """
    Create multiple empty folders under a parent.

    Args:
        parent: Parent folder path
        folder_names: List of folder names to create
        workspace_root: Base workspace directory

    Returns:
        List of absolute paths to created folders

    Example:
        paths = empty_folders("test_abc", ["ADRs", "PLANS", "completed"])
    """
    parent_path = Path(workspace_root) / parent
    parent_path.mkdir(parents=True, exist_ok=True)

    created = []
    for name in folder_names:
        folder_path = parent_path / name
        folder_path.mkdir(exist_ok=True)
        created.append(folder_path.resolve())

    return created


def unique_test_folder(prefix: str = "test", workspace_root: str = "workspace") -> Path:
    """
    Create an empty test folder with a unique name.

    Args:
        prefix: Prefix for folder name
        workspace_root: Base workspace directory

    Returns:
        Absolute path to created folder

    Example:
        root = unique_test_folder("sort_test")
        # Creates: workspace/sort_test_a1b2c3d4/
    """
    folder_name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    folder_path = Path(workspace_root) / folder_name
    folder_path.mkdir(parents=True, exist_ok=True)
    return folder_path.resolve()


def cleanup_folder(path: Path) -> None:
    """Remove a folder and all contents."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
