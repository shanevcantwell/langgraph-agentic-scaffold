import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

class CancellationManager:
    """
    Manages the cancellation state of active workflow runs.

    Maintains a parent→children tree so that cancelling a parent run
    cascades to all descendant children (fork() invocations).
    See #203: BUG-FORK-001.
    """
    _instance = None
    _cancelled_runs: Set[str] = set()
    _parent_to_children: Dict[str, Set[str]] = {}
    _child_to_parent: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CancellationManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def register_child(cls, parent_run_id: str, child_run_id: str):
        """
        Register a parent→child relationship for cascade cancellation.

        Called by invoke_graph() when a fork() request includes a parent_run_id.
        """
        if parent_run_id not in cls._parent_to_children:
            cls._parent_to_children[parent_run_id] = set()
        cls._parent_to_children[parent_run_id].add(child_run_id)
        cls._child_to_parent[child_run_id] = parent_run_id
        logger.info(f"Registered child {child_run_id} under parent {parent_run_id}")

    @classmethod
    def request_cancellation(cls, run_id: str):
        """
        Marks a run_id for cancellation. Cascades to all descendants.
        """
        if run_id in cls._cancelled_runs:
            return  # Already cancelled — avoid infinite recursion on cycles
        logger.info(f"Cancellation requested for run_id: {run_id}")
        cls._cancelled_runs.add(run_id)

        # Cascade to children
        children = cls._parent_to_children.get(run_id, set()).copy()
        for child_id in children:
            logger.info(f"Cascading cancellation to child: {child_id}")
            cls.request_cancellation(child_id)

    @classmethod
    def is_cancelled(cls, run_id: str) -> bool:
        """
        Checks if a run_id has been marked for cancellation.
        """
        return run_id in cls._cancelled_runs

    @classmethod
    def clear_cancellation(cls, run_id: str):
        """
        Removes a run_id from the cancellation set and parent-child registry.
        Called when a run finishes (success or error).
        """
        cls._cancelled_runs.discard(run_id)

        # Remove from parent's children set
        parent_id = cls._child_to_parent.pop(run_id, None)
        if parent_id and parent_id in cls._parent_to_children:
            cls._parent_to_children[parent_id].discard(run_id)
            if not cls._parent_to_children[parent_id]:
                del cls._parent_to_children[parent_id]

        # Remove own children registry (children clear themselves on finish)
        cls._parent_to_children.pop(run_id, None)
