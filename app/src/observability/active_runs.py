"""
Active run registry -- shared state between chat heads and observability.

Chat heads register/deregister runs as they start and complete.
The observability layer reads the registry to discover what's running
(GET /v1/runs/active) and attach event streams.
"""
from typing import Dict, Any, List


class ActiveRunRegistry:
    """Thread-safe-ish registry of currently active workflow runs.

    In practice, all access is from the asyncio event loop (FastAPI handlers),
    so a plain dict suffices.  If that changes, wrap with asyncio.Lock.
    """

    def __init__(self):
        self._runs: Dict[str, Dict[str, Any]] = {}

    def register(self, run_id: str, info: Dict[str, Any]) -> None:
        """Called by chat heads when a run starts."""
        self._runs[run_id] = info

    def update(self, run_id: str, **kwargs) -> None:
        """Update metadata for a running run (e.g. status change)."""
        if run_id in self._runs:
            self._runs[run_id].update(kwargs)

    def deregister(self, run_id: str) -> None:
        """Called by chat heads when a run completes or errors."""
        self._runs.pop(run_id, None)

    def get_active(self) -> List[Dict[str, Any]]:
        """Called by observability to list active runs."""
        return [
            {"run_id": rid, **info}
            for rid, info in self._runs.items()
        ]

    def contains(self, run_id: str) -> bool:
        return run_id in self._runs


# Module-level singleton
active_runs = ActiveRunRegistry()
