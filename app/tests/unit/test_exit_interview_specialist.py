# app/tests/unit/test_exit_interview_specialist.py
"""
Tests for ExitInterviewSpecialist - ADR-CORE-058 Phase 1

Focus on trace-based heuristics that detect obvious failures WITHOUT LLM calls.
These tests verify mechanical verification before expensive LLM evaluation.
"""
from unittest.mock import MagicMock, patch
import pytest

from app.src.specialists.exit_interview_specialist import (
    ExitInterviewSpecialist,
    CompletionEvaluation
)


@pytest.fixture
def exit_interview(initialized_specialist_factory):
    """
    Fixture for an initialized ExitInterviewSpecialist.
    Uses the conftest factory for consistent initialization.
    """
    return initialized_specialist_factory(
        "ExitInterviewSpecialist",
        specialist_name_override="exit_interview"
    )


# =============================================================================
# ADR-CORE-058 Phase 1: Trace-Based Heuristics
# =============================================================================

class TestTraceHeuristics:
    """
    Tests for _evaluate_trace_heuristics() - mechanical verification
    that detects obvious failures without LLM involvement.
    """

    def test_max_iterations_exceeded_returns_incomplete(self, exit_interview):
        """
        ADR-CORE-058: max_iterations_exceeded artifact should immediately
        return INCOMPLETE without needing LLM evaluation.
        """
        artifacts = {
            "max_iterations_exceeded": True,
            "user_request": "Sort files into folders"
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        assert result is not None
        assert result.is_complete is False
        assert "iteration limit" in result.reasoning.lower()
        assert "project_director" in result.recommended_specialists

    def test_failed_operation_no_recovery_returns_incomplete(self, exit_interview):
        """
        ADR-CORE-058: Trace ending with failed operation (no recovery)
        should return INCOMPLETE.
        """
        artifacts = {
            "research_trace_0": [
                {"tool": "list_directory", "args": {}, "success": True},
                {"tool": "read_file", "args": {"path": "/workspace/1.txt"}, "success": True},
                {"tool": "create_directory", "args": {"path": "/workspace/animals"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/1.txt", "destination": "/workspace/animals/1.txt"}, "success": True},
                {"tool": "move_file", "args": {"source": "/workspace/2.txt", "destination": "/workspace/animals/2.txt"}, "success": False, "error": "Hit iteration limit"},
            ]
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        assert result is not None
        assert result.is_complete is False
        assert "move_file" in result.reasoning
        assert "project_director" in result.recommended_specialists

    def test_failed_operation_with_recovery_defers_to_llm(self, exit_interview):
        """
        ADR-CORE-058: If failure occurs but subsequent operations succeed,
        defer to LLM evaluation (return None).
        """
        artifacts = {
            "research_trace_0": [
                {"tool": "read_file", "args": {}, "success": False, "error": "File not found"},
                {"tool": "list_directory", "args": {}, "success": True},  # Recovered
                {"tool": "read_file", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": True},
            ]
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # Should defer to LLM (return None) since there was recovery
        assert result is None

    def test_all_operations_succeeded_defers_to_llm(self, exit_interview):
        """
        ADR-CORE-058: If all trace operations succeeded, defer to LLM
        for semantic verification (we can't tell if the *right* work was done).
        """
        artifacts = {
            "research_trace_0": [
                {"tool": "list_directory", "args": {}, "success": True},
                {"tool": "read_file", "args": {}, "success": True},
                {"tool": "create_directory", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": True},
            ]
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # Should defer to LLM (return None)
        assert result is None

    def test_no_trace_artifacts_defers_to_llm(self, exit_interview):
        """
        ADR-CORE-058: If no research_trace artifacts exist, defer to LLM.
        (Might be a chat task or other non-tool-using specialist.)
        """
        artifacts = {
            "user_request": "What is the capital of France?",
            "gathered_context": "Some context"
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # Should defer to LLM (return None)
        assert result is None

    def test_empty_trace_defers_to_llm(self, exit_interview):
        """
        ADR-CORE-058: Empty trace list should defer to LLM.
        """
        artifacts = {
            "research_trace_0": []
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # Should defer to LLM (return None)
        assert result is None

    def test_multiple_trace_artifacts_combined(self, exit_interview):
        """
        ADR-CORE-058: If multiple research_trace_N artifacts exist,
        they should all be analyzed together.
        """
        artifacts = {
            # First specialist run - partial success
            "research_trace_0": [
                {"tool": "read_file", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": True},
            ],
            # Second specialist run - ended with failure
            "research_trace_1": [
                {"tool": "read_file", "args": {}, "success": True},
                {"tool": "move_file", "args": {}, "success": False, "error": "Permission denied"},
            ]
        }

        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # Should detect the failure in trace_1
        assert result is not None
        assert result.is_complete is False
        assert "move_file" in result.reasoning

    def test_malformed_trace_entries_handled_gracefully(self, exit_interview):
        """
        ADR-CORE-058: Malformed trace entries shouldn't crash the heuristics.
        """
        artifacts = {
            "research_trace_0": [
                {"tool": "read_file", "success": True},  # Missing args
                "not a dict",  # Completely wrong type
                {"tool": "move_file"},  # Missing success key (defaults to True)
                None,  # None entry
            ]
        }

        # Should not raise, should handle gracefully
        result = exit_interview._evaluate_trace_heuristics(artifacts)

        # No explicit failures, should defer to LLM
        assert result is None


# =============================================================================
# Integration: Heuristics in _execute_logic()
# =============================================================================

class TestHeuristicsIntegration:
    """
    Tests that heuristics are properly integrated into _execute_logic()
    and return early without calling LLM when failures are detected.
    """

    def test_max_iterations_skips_llm_call(self, exit_interview):
        """
        When max_iterations_exceeded is present, _execute_logic() should
        return INCOMPLETE without invoking the LLM adapter.
        """
        state = {
            "artifacts": {
                "max_iterations_exceeded": True,
                "user_request": "Sort files"
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        # Mock the LLM adapter to verify it's NOT called
        exit_interview.llm_adapter = MagicMock()

        result = exit_interview._execute_logic(state)

        # LLM should NOT be called
        exit_interview.llm_adapter.invoke.assert_not_called()

        # Result should indicate incomplete
        assert result["task_is_complete"] is False
        assert "heuristic" in result["artifacts"]["exit_interview_result"]["method"]

    def test_failed_trace_skips_llm_call(self, exit_interview):
        """
        When trace shows unrecovered failure, _execute_logic() should
        return INCOMPLETE without invoking the LLM adapter.
        """
        state = {
            "artifacts": {
                "user_request": "Organize files",
                "research_trace_0": [
                    {"tool": "read_file", "args": {}, "success": True},
                    {"tool": "move_file", "args": {}, "success": False, "error": "Failed"},
                ]
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.llm_adapter = MagicMock()

        result = exit_interview._execute_logic(state)

        # LLM should NOT be called
        exit_interview.llm_adapter.invoke.assert_not_called()

        # Result should indicate incomplete
        assert result["task_is_complete"] is False
        assert "heuristic" in result["artifacts"]["exit_interview_result"]["method"]

    def test_clean_trace_proceeds_to_llm(self, exit_interview):
        """
        When trace shows all successes, _execute_logic() should proceed
        to LLM evaluation for semantic verification.
        """
        state = {
            "artifacts": {
                "user_request": "Organize files",
                "research_trace_0": [
                    {"tool": "read_file", "args": {}, "success": True},
                    {"tool": "move_file", "args": {}, "success": True},
                ]
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        # Mock LLM response
        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "All files organized",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        result = exit_interview._execute_logic(state)

        # LLM SHOULD be called (heuristics passed)
        exit_interview.llm_adapter.invoke.assert_called_once()

        # Result should come from LLM
        assert result["task_is_complete"] is True
        # Method should NOT be "heuristic" since LLM was used
        assert result["artifacts"]["exit_interview_result"].get("method") != "heuristic"
