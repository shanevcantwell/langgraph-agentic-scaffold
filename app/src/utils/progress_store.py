"""
Intra-node progress publishing for long-running specialists.

Specialists (PD, TA) call publish() during react_step iterations.
The API layer calls drain() to collect entries for the polling endpoint.
Thread-safe: specialists run in sync threads, API is async.
"""
import threading
from typing import Any, Dict, List

_store: Dict[str, List[Dict[str, Any]]] = {}
_lock = threading.Lock()


def publish(run_id: str, entry: Dict[str, Any]) -> None:
    """Append a progress entry for a run. Called from specialist threads."""
    if not run_id:
        return
    with _lock:
        _store.setdefault(run_id, []).append(entry)


def drain(run_id: str) -> List[Dict[str, Any]]:
    """Pop all entries for a run. Called from API endpoint."""
    with _lock:
        return _store.pop(run_id, [])


def cleanup(run_id: str) -> None:
    """Remove all entries for a run. Called on workflow end."""
    with _lock:
        _store.pop(run_id, None)
