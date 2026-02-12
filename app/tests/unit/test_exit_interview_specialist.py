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

    def test_stray_json_without_is_complete_defaults_to_incomplete(self, exit_interview):
        """
        Issue #150: LLM sometimes returns stray JSON (e.g. prior specialist's tool
        args like {'path': 'categories_test'}) instead of CompletionEvaluation.
        Should default to INCOMPLETE (circuit breaker handles loop prevention),
        not a pydantic crash and not a false-positive completion.
        """
        state = {
            "artifacts": {"user_request": "Sort files"},
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {"path": "categories_test"}  # stray tool args
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is False
        assert "unrelated JSON" in result["artifacts"]["exit_interview_result"]["reasoning"]


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

        # SA should have been called via MCP with verification-focused context
        exit_interview.mcp_client.call.assert_called_once()
        call_kwargs = exit_interview.mcp_client.call.call_args.kwargs
        assert call_kwargs["artifact_key"] == "exit_plan"
        assert "Sort files into categories" in call_kwargs["context"]
        assert "VERIFICATION PLAN" in call_kwargs["context"]  # Issue #129: verification focus

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


# =============================================================================
# Issue #155: Artifact Value Previews
# =============================================================================

class TestArtifactSummary:
    """
    Issue #155: EI should see artifact values, not just key names.

    Previously EI only passed artifact key names to the LLM (e.g., "text_analysis_results")
    which prevented it from distinguishing a successful analysis from an empty/error result.
    """

    def test_artifact_summary_includes_value_previews(self, exit_interview):
        """Artifact summary should include truncated value previews."""
        artifacts = {
            "user_request": "Analyze the text",
            "text_analysis_results": {"summary": "The text discusses AI safety", "word_count": 500},
            "final_response": "Here is the analysis of your text...",
            "_internal_flag": True,  # Should be excluded (underscore prefix)
            "gathered_context": "large context blob",  # Should be excluded
            "context_plan": {"reasoning": "..."},  # Should be excluded
        }

        summary = exit_interview._build_artifact_summary(artifacts)

        # Included artifacts should show values
        assert "text_analysis_results" in summary
        assert "AI safety" in summary  # Value preview
        assert "final_response" in summary
        assert "analysis of your text" in summary  # Value preview

        # Excluded artifacts should NOT appear
        assert "_internal_flag" not in summary
        assert "gathered_context" not in summary
        assert "context_plan" not in summary

    def test_artifact_summary_handles_empty_artifacts(self, exit_interview):
        """Empty artifacts should return a placeholder."""
        summary = exit_interview._build_artifact_summary({})
        assert summary == "[No artifacts produced]"

    def test_artifact_summary_truncates_long_values(self, exit_interview):
        """Long artifact values should be truncated."""
        artifacts = {
            "big_result": "x" * 1000,
        }

        summary = exit_interview._build_artifact_summary(artifacts, max_preview=100)
        assert len(summary) < 200  # Truncated, not 1000 chars
        assert "..." in summary

    def test_artifact_summary_handles_binary(self, exit_interview):
        """Binary artifacts should show size, not content."""
        artifacts = {
            "uploaded_image.png": b"\x89PNG" + b"\x00" * 1000,
        }

        summary = exit_interview._build_artifact_summary(artifacts)
        assert "binary" in summary
        assert "1004 bytes" in summary

    def test_artifact_preview_passed_to_llm_prompt(self, exit_interview):
        """#155: The LLM prompt should contain artifact value previews, not just keys."""
        state = {
            "artifacts": {
                "user_request": "Analyze text",
                "analysis_result": {"quality": "good", "score": 0.95},
            },
            "messages": [],
            "routing_history": ["text_analysis_specialist"]
        }

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "Analysis complete with good quality",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        exit_interview._execute_logic(state)

        # Inspect the prompt sent to LLM
        call_args = exit_interview.llm_adapter.invoke.call_args[0][0]
        prompt_content = call_args.messages[0].content

        # Should contain value preview, not just "analysis_result"
        assert "quality" in prompt_content
        assert "0.95" in prompt_content


# =============================================================================
# Issue #114: EI should NOT clear max_iterations_exceeded
# =============================================================================

class TestExitInterviewSignalPreservation:
    """
    Issue #114: EI should not clear max_iterations_exceeded.

    The consumer (Facilitator) clears the flag, not a bystander (EI).
    EI destroyed the signal before its real consumer could read it.
    """

    def test_ei_does_not_clear_max_iterations_on_complete(self, exit_interview):
        """
        When EI says COMPLETE, it should NOT include max_iterations_exceeded in artifacts.
        """
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "max_iterations_exceeded": True  # Flag was set by PD
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.mcp_client = MagicMock()
        exit_interview.mcp_client.call.return_value = {"artifacts": {"exit_plan": {}}}

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": True,
                "reasoning": "All done",
                "missing_elements": "",
                "recommended_specialists": []
            }
        }

        result = exit_interview._execute_logic(state)

        # EI should NOT set max_iterations_exceeded (doesn't touch the flag)
        assert "max_iterations_exceeded" not in result["artifacts"], (
            "EI should not touch max_iterations_exceeded - consumer (Facilitator) clears it"
        )

    def test_ei_does_not_clear_max_iterations_on_incomplete(self, exit_interview):
        """
        When EI says INCOMPLETE, it should NOT include max_iterations_exceeded in artifacts.

        This is the critical case: if max_iterations_exceeded is True and EI says INCOMPLETE,
        Facilitator needs to see the flag to know this is BENIGN continuation, not correction.
        """
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "max_iterations_exceeded": True  # Flag was set by PD
            },
            "messages": [],
            "routing_history": ["project_director"]
        }

        exit_interview.mcp_client = MagicMock()
        exit_interview.mcp_client.call.return_value = {"artifacts": {"exit_plan": {}}}

        exit_interview.llm_adapter = MagicMock()
        exit_interview.llm_adapter.invoke.return_value = {
            "json_response": {
                "is_complete": False,
                "reasoning": "Only half done",
                "missing_elements": "More work needed",
                "recommended_specialists": ["project_director"]
            }
        }

        result = exit_interview._execute_logic(state)

        # EI should NOT set max_iterations_exceeded (doesn't touch the flag)
        assert "max_iterations_exceeded" not in result["artifacts"], (
            "EI should not touch max_iterations_exceeded - Facilitator needs to see it "
            "to distinguish BENIGN continuation from correction cycle"
        )