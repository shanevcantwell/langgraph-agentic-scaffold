import os
from pathlib import Path
from typing import Dict, Any


class CodeWriteSpecialist:
    """
    Specialist that can copy or update code files:
      - pick a source path from the repo
      - choose a destination path
      - write or update code
    """

    def __init__(self, base_dir: str = "/workspace"):
        self.base_dir = Path(base_dir)

    def _resolve_path(self, rel_path: str) -> Path:
        """Make sure path is inside workspace for safety."""
        path = (self.base_dir / rel_path.lstrip("/")).resolve()
        if not str(path).startswith(str(self.base_dir)):
            raise ValueError("Invalid path outside workspace")
        return path

    def run(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        task = {
            "source_path": "relative/path/to/file.py",
            "destination_path": "relative/path/to/dest.py",
            "code": "new code to write or append",
            "mode": "copy|overwrite|append"
        }
        """
        try:
            src = self
