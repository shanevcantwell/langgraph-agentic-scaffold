import logging
from typing import Set

logger = logging.getLogger(__name__)

class CancellationManager:
    """
    Manages the cancellation state of active workflow runs.
    This is a simple in-memory store for run_ids that have been requested to cancel.
    """
    _instance = None
    _cancelled_runs: Set[str] = set()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CancellationManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def request_cancellation(cls, run_id: str):
        """
        Marks a run_id for cancellation.
        """
        logger.info(f"Cancellation requested for run_id: {run_id}")
        cls._cancelled_runs.add(run_id)

    @classmethod
    def is_cancelled(cls, run_id: str) -> bool:
        """
        Checks if a run_id has been marked for cancellation.
        """
        return run_id in cls._cancelled_runs

    @classmethod
    def clear_cancellation(cls, run_id: str):
        """
        Removes a run_id from the cancellation set (cleanup).
        """
        if run_id in cls._cancelled_runs:
            cls._cancelled_runs.remove(run_id)
