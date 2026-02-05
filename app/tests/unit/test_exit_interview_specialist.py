# app/tests/unit/test_exit_interview_specialist.py
"""
Tests for ExitInterviewSpecialist - ADR-CORE-061 Pure LLM Evaluator

ADR-CORE-061 Refactor: Exit Interview is now a PURE semantic completion evaluator.
All infrastructure heuristics (max_iterations, trace stutter, unrecovered failures)
have been moved to the Interrupt Classifier (graph_orchestrator.py).

Exit Interview answers ONE question: "Is the task semantically complete?"

For heuristic tests, see test_interrupt_classifier.py.
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
# ADR-CORE-061: Exit Interview is Pure LLM Evaluator
# =============================================================================
# NOTE: TestTraceHeuristics and TestHeuristicsIntegration were REMOVED
# as part of ADR-CORE-061. The heuristic functionality has been moved to
# Interrupt Classifier (graph_orchestrator.classify_interrupt).
#
# See test_interrupt_classifier.py for those tests.
# =============================================================================


class TestExitInterviewLLMEvaluation:
    """
    Tests for Exit Interview's LLM-based semantic completion evaluation.
    After ADR-CORE-061, this is the ONLY evaluation Exit Interview performs.
    """

    def test_llm_evaluates_completion(self, exit_interview):
        """
        Exit Interview should always call LLM for semantic evaluation.
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

        # LLM SHOULD be called
        exit_interview.llm_adapter.invoke.assert_called_once()

        # Result should come from LLM
        assert result["task_is_complete"] is True

    def test_llm_returns_incomplete(self, exit_interview):
        """
        When LLM determines task is incomplete, result reflects that.
        """
        state = {
            "artifacts": {
                "user_request": "Sort all files by category"
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": False,
                "reasoning": "Files have not been sorted yet",
                "missing_elements": "Need to actually sort the files",
                "recommended_specialists": ["project_director"]
            }
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is False
        assert "project_director" in result["scratchpad"]["recommended_specialists"]


# =============================================================================
# ADR-CORE-061: Exit Interview Purity (Post-Refactor)
# =============================================================================

class TestExitInterviewPurity:
    """
    Tests asserting Exit Interview is a PURE LLM semantic completion evaluator
    after ADR-CORE-061 refactor.

    These tests WILL FAIL until heuristics are extracted to Interrupt Classifier.

    The principle: Exit Interview answers ONE question: "Is the task done?"
    It should NOT contain infrastructure concerns like:
    - max_iterations_exceeded (arbitrary limit, not semantic)
    - trace stutter detection (health concern, not completion)
    - unrecovered failure detection (infrastructure, not semantic)

    All of those belong in Interrupt Classifier (procedural) or
    Interrupt Evaluator (LLM judgment on recoverability).
    """

    def test_exit_interview_has_no_check_heuristics_method(self):
        """
        ADR-CORE-061: _check_heuristics() belongs in Interrupt Classifier.

        Exit Interview should not have heuristic checking - it's a pure
        LLM evaluator. Heuristics are infrastructure concerns that should
        be handled before Exit Interview even sees the state.
        """
        assert not hasattr(ExitInterviewSpecialist, '_check_heuristics'), \
            "Exit Interview should not have _check_heuristics after ADR-CORE-061 refactor"

    def test_exit_interview_has_no_evaluate_trace_heuristics_method(self):
        """
        ADR-CORE-061: _evaluate_trace_heuristics() belongs in Interrupt Classifier.

        Trace inspection for failures is an infrastructure concern, not
        semantic completion evaluation.
        """
        assert not hasattr(ExitInterviewSpecialist, '_evaluate_trace_heuristics'), \
            "Exit Interview should not have _evaluate_trace_heuristics after ADR-CORE-061 refactor"

    def test_exit_interview_has_no_stutter_detection(self):
        """
        ADR-CORE-061: Stutter detection belongs in Interrupt Classifier.

        Detecting trace drift/stutter (via semantic-chunker MCP) is a
        health concern about whether the model is making progress, not
        a semantic question about task completion.
        """
        assert not hasattr(ExitInterviewSpecialist, '_detect_trace_stutter'), \
            "Stutter detection belongs in Interrupt Classifier, not Exit Interview"

    def test_exit_interview_only_evaluates_completion(self, exit_interview):
        """
        ADR-CORE-061: Exit Interview should ONLY have _evaluate_completion.

        After refactor, Exit Interview is a pure LLM semantic evaluator.
        The only evaluation method should be _evaluate_completion().
        """
        # Should have the LLM evaluation method
        assert hasattr(exit_interview, '_evaluate_completion'), \
            "Exit Interview must have _evaluate_completion for LLM semantic evaluation"

        # Should NOT have any heuristic methods
        heuristic_methods = [
            '_check_heuristics',
            '_evaluate_trace_heuristics',
            '_detect_trace_stutter',
            '_detect_unrecovered_failures',
        ]
        for method in heuristic_methods:
            assert not hasattr(exit_interview, method), \
                f"Exit Interview should not have {method} - belongs in Interrupt Classifier"


# =============================================================================
# Issue #115: On-Demand SA Call for exit_plan
# =============================================================================

class TestExitInterviewSAIntegration:
    """
    Tests for Exit Interview's on-demand SA call to produce exit_plan (Issue #115).

    EI is graph-wired (not Router-selected), so it can't use requires_artifacts.
    Instead, EI calls SA via MCP when exit_plan is missing.
    """

    def test_calls_sa_when_exit_plan_missing(self, exit_interview):
        """
        When exit_plan is not in artifacts, EI should call SA via MCP.
        """
        state = {
            "artifacts": {
                "user_request": "Sort files into categories"
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        # Mock MCP client
        exit_interview.mcp_client = MagicMock()
        exit_interview.mcp_client.call.return_value = {
            "artifacts": {
                "exit_plan": {
                    "plan_summary": "Sort files by type",
                    "execution_steps": ["Identify types", "Create dirs", "Move files"]
                }
            }
        }

        # Mock LLM for completion evaluation
        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "Files sorted",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        result = exit_interview._execute_logic(state)

        # SA should have been called via MCP
        exit_interview.mcp_client.call.assert_called_once_with(
            "systems_architect",
            "create_plan",
            context="Sort files into categories",
            artifact_key="exit_plan"
        )

        # exit_plan should be persisted in artifacts
        assert "exit_plan" in result["artifacts"]
        assert result["artifacts"]["exit_plan"]["plan_summary"] == "Sort files by type"

    def test_skips_sa_call_when_exit_plan_exists(self, exit_interview):
        """
        When exit_plan already exists, EI should NOT call SA.
        """
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {
                    "plan_summary": "Existing plan",
                    "execution_steps": ["Step 1"]
                }
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.mcp_client = MagicMock()
        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "Done",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        exit_interview._execute_logic(state)

        # SA should NOT have been called
        exit_interview.mcp_client.call.assert_not_called()

    def test_handles_sa_mcp_call_failure_gracefully(self, exit_interview):
        """
        If SA MCP call fails, EI should proceed without exit_plan.
        """
        state = {
            "artifacts": {
                "user_request": "Sort files"
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.mcp_client = MagicMock()
        exit_interview.mcp_client.call.side_effect = Exception("SA unavailable")

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "Completed without plan",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        # Should not raise - EI handles missing exit_plan gracefully
        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        # exit_plan should be empty dict (not None)
        assert result["artifacts"]["exit_plan"] == {}

    def test_persists_exit_plan_on_incomplete(self, exit_interview):
        """
        When task is incomplete, exit_plan should still be persisted for next iteration.
        """
        state = {
            "artifacts": {
                "user_request": "Sort all files"
            },
            "messages": [],
            "routing_history": []
        }

        exit_interview.mcp_client = MagicMock()
        exit_interview.mcp_client.call.return_value = {
            "artifacts": {
                "exit_plan": {"plan_summary": "Sort plan", "execution_steps": []}
            }
        }

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": False,
                "reasoning": "No files sorted yet",
                "missing_elements": "Need to actually sort",
                "recommended_specialists": ["project_director"]
            }
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is False
        # exit_plan should be persisted even on incomplete
        assert "exit_plan" in result["artifacts"]
        assert result["artifacts"]["exit_plan"]["plan_summary"] == "Sort plan"