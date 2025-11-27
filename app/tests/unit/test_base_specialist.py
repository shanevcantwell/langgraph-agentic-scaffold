# app/tests/unit/test_base_specialist.py
"""
Tests for BaseSpecialist enforcement and safety mechanisms.
"""
import pytest
from unittest.mock import MagicMock

from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import SpecialistError


class ConcreteSpecialist(BaseSpecialist):
    """Test implementation of BaseSpecialist."""

    def __init__(self, return_value: dict):
        super().__init__("test_specialist", {"is_enabled": True})
        self._return_value = return_value

    def _execute_logic(self, state: dict):
        return self._return_value


class TestControlSignalEnforcement:
    """
    Tests that BaseSpecialist enforces correct placement of control signals.

    task_is_complete MUST be at root level for check_task_completion() to work.
    If a specialist puts it in scratchpad, it's invisible to the orchestrator.
    """

    def test_task_is_complete_at_root_level_passes_validation(self):
        """
        When task_is_complete is correctly at root level, validation passes.
        """
        specialist = ConcreteSpecialist({
            "messages": [],
            "task_is_complete": True,
        })

        result = specialist.execute({})

        assert result.get("task_is_complete") is True

    def test_task_is_complete_in_scratchpad_raises_error(self):
        """
        FAIL-FAST: When task_is_complete is mistakenly in scratchpad,
        BaseSpecialist raises SpecialistError immediately.

        This prevents the loop bug where check_task_completion() can't see
        the signal and Router keeps routing back to the same specialist.
        """
        specialist = ConcreteSpecialist({
            "messages": [],
            "scratchpad": {
                "task_is_complete": True,
                "other_data": "preserved"
            }
        })

        with pytest.raises(SpecialistError) as exc_info:
            specialist.execute({})

        assert "INVARIANT VIOLATION" in str(exc_info.value)
        assert "task_is_complete" in str(exc_info.value)

    def test_no_task_is_complete_passes_validation(self):
        """
        When no task_is_complete signal exists, validation passes.
        """
        specialist = ConcreteSpecialist({
            "messages": [],
            "scratchpad": {"some_data": "value"}
        })

        result = specialist.execute({})

        assert result.get("task_is_complete") is None
        assert result.get("scratchpad") == {"some_data": "value"}
