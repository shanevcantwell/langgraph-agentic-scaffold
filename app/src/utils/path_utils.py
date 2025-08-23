# app/src/utils/path_utils.py
import os
from pathlib import Path

def get_project_root() -> Path:
    """
    Finds the project root by searching upwards for a marker file ('pyproject.toml').
    This makes path resolution independent of the current working directory.
    """
    current_path = Path(__file__).resolve()
    while current_path != current_path.parent:
        if (current_path / 'pyproject.toml').exists():
            return current_path
        current_path = current_path.parent
    raise FileNotFoundError("Project root with 'pyproject.toml' not found. Cannot determine application root.")

PROJECT_ROOT = get_project_root()
APP_ROOT = PROJECT_ROOT / "app"