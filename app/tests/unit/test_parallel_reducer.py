import pytest
from unittest.mock import MagicMock
from app.src.graph.state import reduce_parallel_tasks

class TestParallelTasksReducer:
    def test_initialization(self):
        """Test initializing the list with a list update."""
        current = []
        update = ["A", "B"]
        result = reduce_parallel_tasks(current, update)
        assert result == ["A", "B"]

    def test_removal(self):
        """Test removing an item with a string update."""
        current = ["A", "B"]
        update = "A"
        result = reduce_parallel_tasks(current, update)
        assert result == ["B"]

    def test_removal_last_item(self):
        """Test removing the last item results in empty list."""
        current = ["B"]
        update = "B"
        result = reduce_parallel_tasks(current, update)
        assert result == []

    def test_removal_non_existent(self):
        """Test removing an item that doesn't exist (idempotency)."""
        current = ["A", "B"]
        update = "C"
        result = reduce_parallel_tasks(current, update)
        assert result == ["A", "B"]

    def test_reinitialization(self):
        """Test overwriting existing list with new list."""
        current = ["A"]
        update = ["C", "D"]
        result = reduce_parallel_tasks(current, update)
        assert result == ["C", "D"]
