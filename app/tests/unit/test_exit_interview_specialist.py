# app/tests/unit/test_exit_interview_specialist.py
"""
Tests for ExitInterviewSpecialist — react_step verification gate (#195).

EI uses prompt-prix react_step to inspect filesystem and artifacts, then
calls DONE with a structured CompletionEvaluation. There is no fallback
single-pass path; if prompt-prix is unavailable, EI returns an honest
"cannot verify" signal.

For artifact tool tests (list_artifacts, retrieve_artifact), see
test_artifact_tools.py.
"""
from unittest.mock import MagicMock, patch
import pytest

from app.src.specialists.exit_interview_specialist import (
    ExitInterviewSpecialist,
    CompletionEvaluation,
)


@pytest.fixture
def exit_interview(initialized_specialist_factory):
    """
    Fixture for an initialized ExitInterviewSpecialist.
    Uses the conftest factory for consistent initialization.
    """
    ei = initialized_specialist_factory(
        "ExitInterviewSpecialist",
        specialist_name_override="exit_interview"
    )
    return ei


@pytest.fixture
def react_ready_ei(exit_interview):
    """
    EI with mocked external_mcp_client so is_react_available() returns True.
    Most tests need this since there's no fallback path.
    """
    mock_client = MagicMock()
    mock_client.is_connected.return_value = True
    exit_interview.external_mcp_client = mock_client
    return exit_interview


def _make_react_step_done(is_complete, reasoning, missing_elements="", recommended=None):
    """Helper: build a call_react_step return value where DONE was called."""
    return {
        "completed": True,
        "done_args": {
            "is_complete": is_complete,
            "reasoning": reasoning,
            "missing_elements": missing_elements,
            "recommended_specialists": recommended or [],
        },
        "pending_tool_calls": [],
        "call_counter": 1,
    }


def _make_react_step_tool_call(tool_name, tool_args, call_id="tc_1"):
    """Helper: build a call_react_step return value with a pending tool call."""
    return {
        "completed": False,
        "pending_tool_calls": [
            {"id": call_id, "name": tool_name, "args": tool_args}
        ],
        "call_counter": 1,
    }


# =============================================================================
# react_step Verification Path
# =============================================================================

class TestReactStepVerification:
    """
    Tests for EI's react_step verification loop (#195).
    EI calls tools, inspects results, then calls DONE.
    """

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_complete_evaluation(self, mock_call_react_step, react_ready_ei):
        """EI verifies task complete via react_step tool loop."""
        state = {
            "artifacts": {
                "user_request": "Organize files",
                "exit_plan": {"plan_summary": "Check files organized"},
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        # Iteration 1: model calls list_directory
        # Iteration 2: model calls DONE(complete)
        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(True, "All files organized correctly"),
        ]

        # Mock external tool dispatch for list_directory
        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="file1.txt\nfile2.txt\ncategory_a/",
        ):
            result = react_ready_ei._execute_logic(state)

        assert result["task_is_complete"] is True
        assert result["artifacts"]["exit_interview_result"]["is_complete"] is True
        assert "organized" in result["artifacts"]["exit_interview_result"]["reasoning"]

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_incomplete_evaluation(self, mock_call_react_step, react_ready_ei):
        """EI marks task incomplete when verification finds missing work."""
        state = {
            "artifacts": {
                "user_request": "Sort all files by category",
                "exit_plan": {"plan_summary": "Verify sorting"},
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(
                False,
                "Files have not been sorted yet",
                missing_elements="Need to actually sort the files",
                recommended=["project_director"],
            ),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="unsorted_file.txt\nanother.txt",
        ):
            result = react_ready_ei._execute_logic(state)

        assert result["task_is_complete"] is False
        assert "project_director" in result["scratchpad"]["recommended_specialists"]

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_max_iterations_defaults_to_incomplete(self, mock_call_react_step, react_ready_ei):
        """When react_step loop exhausts iterations without DONE, result is incomplete."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {},
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        # Every iteration returns a tool call, never DONE
        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": f"/dir{i}"})
            for i in range(10)  # More than MAX_ITERATIONS
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="some files",
        ):
            result = react_ready_ei._execute_logic(state)

        assert result["task_is_complete"] is False
        assert "iterations" in result["artifacts"]["exit_interview_result"]["reasoning"]


# =============================================================================
# Tool-Use-Before-DONE Guard (#193)
# =============================================================================

class TestToolUseBeforeDone:
    """
    #193: EI must call at least one verification tool before calling DONE.
    If the model tries to DONE immediately, EI nudges it to verify first.
    """

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_done_before_tool_use_triggers_nudge(self, mock_call_react_step, react_ready_ei):
        """DONE on first call (no prior tool use) → nudge → model retries with tool use."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {},
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        mock_call_react_step.side_effect = [
            # First: model tries DONE without tool use
            _make_react_step_done(True, "Looks complete"),
            # Second: model uses a tool after nudge
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            # Third: model calls DONE after verification
            _make_react_step_done(True, "Verified files are sorted"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="category_a/\ncategory_b/",
        ):
            result = react_ready_ei._execute_logic(state)

        # Should have called react_step 3 times (nudge + tool + done)
        assert mock_call_react_step.call_count == 3
        assert result["task_is_complete"] is True

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_repeated_done_without_real_tool_keeps_nudging(self, mock_call_react_step, react_ready_ei):
        """DONE twice in a row (no real tool use between) → nudge fires both times."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {},
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        mock_call_react_step.side_effect = [
            # First: DONE without tool use → nudge (SYSTEM entry added)
            _make_react_step_done(True, "Looks complete"),
            # Second: DONE again — trace has SYSTEM but no real tool → nudge again
            _make_react_step_done(True, "Still looks complete"),
            # Third: model finally uses a real tool
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            # Fourth: DONE after real verification
            _make_react_step_done(True, "Verified after inspection"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="category_a/\ncategory_b/",
        ):
            result = react_ready_ei._execute_logic(state)

        # 4 calls: nudge, nudge again, tool, done
        assert mock_call_react_step.call_count == 4
        assert result["task_is_complete"] is True


# =============================================================================
# Prompt-prix Unavailability (#195)
# =============================================================================

class TestPromptPrixUnavailable:
    """
    #195: When prompt-prix is unavailable, EI returns honest "cannot verify"
    with task_is_complete=True (no degraded single-pass fallback).
    """

    def test_unavailable_returns_complete_with_message(self, exit_interview):
        """No external_mcp_client → cannot verify → defaults to complete."""
        state = {
            "artifacts": {"user_request": "Sort files"},
            "messages": [],
            "routing_history": ["project_director"],
        }
        # No external_mcp_client set → is_react_available returns False
        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        assert "unavailable" in result["artifacts"]["exit_interview_result"]["reasoning"]

    def test_disconnected_returns_complete_with_message(self, exit_interview):
        """prompt-prix disconnected → cannot verify → defaults to complete."""
        mock_client = MagicMock()
        mock_client.is_connected.return_value = False  # prompt-prix down
        exit_interview.external_mcp_client = mock_client

        state = {
            "artifacts": {"user_request": "Sort files"},
            "messages": [],
            "routing_history": ["project_director"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        assert "unavailable" in result["artifacts"]["exit_interview_result"]["reasoning"]


# =============================================================================
# Purity: No Infrastructure Heuristics
# =============================================================================

class TestExitInterviewPurity:
    """
    Exit Interview is a pure verification agent.
    No infrastructure heuristics (those belong in Interrupt Classifier).
    """

    def test_no_heuristic_methods(self):
        """EI should not have any heuristic methods (ADR-CORE-061)."""
        heuristic_methods = [
            '_check_heuristics',
            '_evaluate_trace_heuristics',
            '_detect_trace_stutter',
            '_detect_unrecovered_failures',
        ]
        for method in heuristic_methods:
            assert not hasattr(ExitInterviewSpecialist, method), \
                f"Exit Interview should not have {method} — belongs in Interrupt Classifier"

    def test_has_verify_method(self):
        """EI should have _verify (react_step loop) as its core evaluation."""
        assert hasattr(ExitInterviewSpecialist, '_verify'), \
            "Exit Interview must have _verify for react_step verification"

    def test_no_evaluate_completion_method(self):
        """#195: _evaluate_completion (old single-pass path) should not exist."""
        assert not hasattr(ExitInterviewSpecialist, '_evaluate_completion'), \
            "Exit Interview should not have _evaluate_completion — removed in #195"

    def test_no_build_artifact_summary_method(self):
        """#195: _build_artifact_summary moved to mcp/artifact_tools.py."""
        assert not hasattr(ExitInterviewSpecialist, '_build_artifact_summary'), \
            "_build_artifact_summary moved to shared mcp/artifact_tools.py"


# =============================================================================
# Issue #115: On-Demand SA Call for exit_plan
# =============================================================================

class TestExitInterviewSAIntegration:
    """
    Tests for EI's on-demand SA call to produce exit_plan (Issue #115).
    EI calls SA via MCP when exit_plan is missing from artifacts.
    """

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_calls_sa_when_exit_plan_missing(self, mock_call_react_step, react_ready_ei):
        """When exit_plan is not in artifacts, EI should call SA via MCP."""
        state = {
            "artifacts": {
                "user_request": "Sort files into categories"
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        # Mock SA MCP client
        react_ready_ei.mcp_client = MagicMock()
        react_ready_ei.mcp_client.call.return_value = {
            "artifacts": {
                "exit_plan": {
                    "plan_summary": "Sort files by type",
                    "execution_steps": ["Identify types", "Create dirs", "Move files"],
                }
            }
        }

        # react_step: tool use → DONE
        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(True, "Files sorted"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="category_a/\ncategory_b/",
        ):
            result = react_ready_ei._execute_logic(state)

        # SA should have been called via MCP
        react_ready_ei.mcp_client.call.assert_called_once()
        call_args = react_ready_ei.mcp_client.call.call_args
        assert call_args[1]["artifact_key"] == "exit_plan"
        assert "Sort files into categories" in call_args[1]["context"]
        assert "VERIFICATION PLAN" in call_args[1]["context"]

        # exit_plan should be in result artifacts
        assert "exit_plan" in result["artifacts"]
        assert result["artifacts"]["exit_plan"]["plan_summary"] == "Sort files by type"

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_skips_sa_call_when_exit_plan_exists(self, mock_call_react_step, react_ready_ei):
        """When exit_plan already exists, EI should NOT call SA."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {
                    "plan_summary": "Existing plan",
                    "execution_steps": ["Step 1"],
                },
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        react_ready_ei.mcp_client = MagicMock()

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_artifacts", {}),
            _make_react_step_done(True, "Done"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_artifact_tool",
            return_value="Artifacts:\n  user_request: str (10 chars)",
        ):
            react_ready_ei._execute_logic(state)

        # SA should NOT have been called
        react_ready_ei.mcp_client.call.assert_not_called()

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_handles_sa_mcp_call_failure_gracefully(self, mock_call_react_step, react_ready_ei):
        """If SA MCP call fails, EI should proceed without exit_plan."""
        state = {
            "artifacts": {"user_request": "Sort files"},
            "messages": [],
            "routing_history": ["project_director"],
        }

        react_ready_ei.mcp_client = MagicMock()
        react_ready_ei.mcp_client.call.side_effect = Exception("SA unavailable")

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(True, "Completed without plan"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="files here",
        ):
            result = react_ready_ei._execute_logic(state)

        assert result["task_is_complete"] is True
        # exit_plan should be empty dict (not None)
        assert result["artifacts"]["exit_plan"] == {}

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_persists_exit_plan_on_incomplete(self, mock_call_react_step, react_ready_ei):
        """When task is incomplete, exit_plan should still be persisted for next iteration."""
        state = {
            "artifacts": {"user_request": "Sort all files"},
            "messages": [],
            "routing_history": [],
        }

        react_ready_ei.mcp_client = MagicMock()
        react_ready_ei.mcp_client.call.return_value = {
            "artifacts": {
                "exit_plan": {"plan_summary": "Sort plan", "execution_steps": []}
            }
        }

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(
                False,
                "No files sorted yet",
                missing_elements="Need to actually sort",
                recommended=["project_director"],
            ),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="unsorted_file.txt",
        ):
            result = react_ready_ei._execute_logic(state)

        assert result["task_is_complete"] is False
        assert "exit_plan" in result["artifacts"]
        assert result["artifacts"]["exit_plan"]["plan_summary"] == "Sort plan"


# =============================================================================
# Issue #114: EI should NOT clear max_iterations_exceeded
# =============================================================================

class TestExitInterviewSignalPreservation:
    """
    Issue #114: EI should not clear max_iterations_exceeded.
    The consumer (Facilitator) clears the flag, not a bystander (EI).
    """

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_ei_does_not_clear_max_iterations_on_complete(self, mock_call_react_step, react_ready_ei):
        """When EI says COMPLETE, it should NOT include max_iterations_exceeded in artifacts."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {},
                "max_iterations_exceeded": True,
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(True, "All done"),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="sorted_files/",
        ):
            result = react_ready_ei._execute_logic(state)

        assert "max_iterations_exceeded" not in result["artifacts"], (
            "EI should not touch max_iterations_exceeded — consumer (Facilitator) clears it"
        )

    @patch("app.src.specialists.exit_interview_specialist.call_react_step")
    def test_ei_does_not_clear_max_iterations_on_incomplete(self, mock_call_react_step, react_ready_ei):
        """When EI says INCOMPLETE, max_iterations_exceeded should not be in result artifacts."""
        state = {
            "artifacts": {
                "user_request": "Sort files",
                "exit_plan": {},
                "max_iterations_exceeded": True,
            },
            "messages": [],
            "routing_history": ["project_director"],
        }

        mock_call_react_step.side_effect = [
            _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
            _make_react_step_done(
                False,
                "Only half done",
                missing_elements="More work needed",
                recommended=["project_director"],
            ),
        ]

        with patch(
            "app.src.specialists.exit_interview_specialist.dispatch_external_tool",
            return_value="unsorted_file.txt",
        ):
            result = react_ready_ei._execute_logic(state)

        assert "max_iterations_exceeded" not in result["artifacts"], (
            "EI should not touch max_iterations_exceeded — Facilitator needs to see it "
            "to distinguish BENIGN continuation from correction cycle"
        )


# =============================================================================
# CompletionEvaluation Schema
# =============================================================================

class TestCompletionEvaluationSchema:
    """Tests for the CompletionEvaluation Pydantic model."""

    def test_minimal_fields(self):
        """is_complete and reasoning are required; others have defaults."""
        eval = CompletionEvaluation(is_complete=True, reasoning="Done")
        assert eval.is_complete is True
        assert eval.reasoning == "Done"
        assert eval.missing_elements == ""
        assert eval.recommended_specialists == []

    def test_all_fields(self):
        """All fields populated."""
        eval = CompletionEvaluation(
            is_complete=False,
            reasoning="Not done",
            missing_elements="Need more work",
            recommended_specialists=["project_director"],
        )
        assert eval.is_complete is False
        assert eval.missing_elements == "Need more work"
        assert eval.recommended_specialists == ["project_director"]


# =============================================================================
# Routable Specialists Enum
# =============================================================================

class TestRoutableSpecialistsEnum:
    """Test dynamic enum injection for recommended_specialists in DONE schema."""

    def test_build_tool_params_adds_enum(self, exit_interview):
        """When routable_specialists set, DONE schema has enum constraint."""
        exit_interview.set_routable_specialists(["project_director", "web_builder"])
        params = exit_interview._build_tool_params()

        done_items = params["DONE"]["properties"]["recommended_specialists"]["items"]
        assert done_items["enum"] == ["project_director", "web_builder"]

    def test_build_tool_params_no_enum_without_routable(self, exit_interview):
        """Without routable_specialists, DONE schema has no enum."""
        params = exit_interview._build_tool_params()

        done_items = params["DONE"]["properties"]["recommended_specialists"]
        assert "enum" not in done_items.get("items", {})


# =============================================================================
# Config-Driven max_iterations
# =============================================================================

class TestMaxIterationsConfig:
    """max_iterations should be configurable per specialist via config.yaml."""

    def test_default_max_iterations(self, exit_interview):
        """Without config, uses DEFAULT_MAX_ITERATIONS (8)."""
        assert exit_interview._get_max_iterations() == 8

    def test_config_overrides_default(self, initialized_specialist_factory):
        """config.yaml max_iterations overrides the class default."""
        ei = initialized_specialist_factory(
            "ExitInterviewSpecialist",
            specialist_name_override="exit_interview",
            config_override={"max_iterations": 12},
        )
        assert ei._get_max_iterations() == 12


# =============================================================================
# #225: Signal-Based Fast Path
# =============================================================================

class TestSignalBasedFastPath:
    """
    #225: EI reads PD's completion_signal artifact and short-circuits
    the SA exit_plan + react_step verification chain.
    """

    def test_completed_signal_accepts(self, exit_interview):
        """COMPLETED signal → task_is_complete=True, routes to END."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
                "completion_signal": {
                    "status": "COMPLETED",
                    "summary": "Full report written to artifacts.",
                },
            },
            "routing_history": ["project_director", "signal_processor_specialist"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        ei_result = result["artifacts"]["exit_interview_result"]
        assert ei_result["is_complete"] is True
        assert "COMPLETED" in ei_result["reasoning"]

    def test_partial_signal_retries(self, exit_interview):
        """PARTIAL signal → task_is_complete=False, routes PD for retry."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
                "completion_signal": {
                    "status": "PARTIAL",
                    "summary": "Hit 50 iteration limit, 3 of 5 sources analyzed.",
                },
            },
            "routing_history": ["project_director"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is False
        ei_result = result["artifacts"]["exit_interview_result"]
        assert ei_result["is_complete"] is False
        assert "PARTIAL" in ei_result["reasoning"]
        assert ei_result["recommended_specialists"] == ["project_director"]
        assert result["scratchpad"]["recommended_specialists"] == ["project_director"]
        assert result["scratchpad"]["exit_interview_incomplete"] is True

    def test_blocked_signal_aborts(self, exit_interview):
        """BLOCKED signal → task_is_complete=True + termination_reason."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
                "completion_signal": {
                    "status": "BLOCKED",
                    "summary": "Stagnation: repeated web_search with same args.",
                },
            },
            "routing_history": ["project_director"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        ei_result = result["artifacts"]["exit_interview_result"]
        assert ei_result["is_complete"] is False
        assert "termination_reason" in result["scratchpad"]

    def test_error_signal_aborts(self, exit_interview):
        """ERROR signal → task_is_complete=True + termination_reason."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
                "completion_signal": {
                    "status": "ERROR",
                    "summary": "MCP connection timeout after 3 retries.",
                },
            },
            "routing_history": ["project_director"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        ei_result = result["artifacts"]["exit_interview_result"]
        assert ei_result["is_complete"] is False
        assert "termination_reason" in result["scratchpad"]
        assert "MCP connection timeout" in result["scratchpad"]["termination_reason"]

    def test_no_signal_falls_through(self, react_ready_ei):
        """No completion_signal → existing verification chain runs."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
            },
            "routing_history": ["project_director"],
        }

        # EI requires at least one real tool call before DONE.
        # Simulate: first call returns a tool call, second returns DONE.
        with patch(
            "app.src.specialists.exit_interview_specialist.call_react_step",
            side_effect=[
                _make_react_step_tool_call("list_artifacts", {}),
                _make_react_step_done(
                    is_complete=True,
                    reasoning="Verified complete",
                ),
            ],
        ) as mock_react:
            result = react_ready_ei._execute_logic(state)

        assert mock_react.call_count == 2
        assert result["task_is_complete"] is True

    def test_unrecognized_status_falls_through(self, react_ready_ei):
        """Unknown status in completion_signal → falls through to verification chain."""
        state = {
            "artifacts": {
                "user_request": "Research AI safety",
                "completion_signal": {
                    "status": "UNKNOWN_STATUS",
                    "summary": "Something unexpected.",
                },
            },
            "routing_history": ["project_director"],
        }

        with patch(
            "app.src.specialists.exit_interview_specialist.call_react_step",
            side_effect=[
                _make_react_step_tool_call("list_artifacts", {}),
                _make_react_step_done(
                    is_complete=True,
                    reasoning="Verified complete",
                ),
            ],
        ) as mock_react:
            result = react_ready_ei._execute_logic(state)

        assert mock_react.call_count == 2
        assert result["task_is_complete"] is True


# =============================================================================
# #243: Artifact-Presence Fast Path for Spoke Specialists
# =============================================================================

class TestArtifactPresenceFastPath:
    """
    #243: Spoke specialists declare produces_artifacts in config.
    EI checks artifact existence and fast-paths to complete without LLM.
    """

    def test_artifact_present_accepts(self, exit_interview):
        """Declared artifact exists and is non-empty → task_is_complete=True."""
        exit_interview.set_produces_artifacts({"web_builder": ["html_document.html"]})

        state = {
            "artifacts": {
                "user_request": "Build a dashboard",
                "html_document.html": "<html><body>Dashboard</body></html>",
            },
            "routing_history": ["web_builder"],
        }

        result = exit_interview._execute_logic(state)

        assert result["task_is_complete"] is True
        ei_result = result["artifacts"]["exit_interview_result"]
        assert ei_result["is_complete"] is True
        assert "web_builder" in ei_result["reasoning"]
        assert "html_document.html" in ei_result["reasoning"]

    def test_artifact_missing_falls_through(self, react_ready_ei):
        """Declared artifact not in state → falls through to legacy verification."""
        react_ready_ei.set_produces_artifacts({"web_builder": ["html_document.html"]})

        state = {
            "artifacts": {
                "user_request": "Build a dashboard",
            },
            "routing_history": ["web_builder"],
        }

        with patch(
            "app.src.specialists.exit_interview_specialist.call_react_step",
            side_effect=[
                _make_react_step_tool_call("list_artifacts", {}),
                _make_react_step_done(False, "No HTML produced", missing_elements="html_document.html"),
            ],
        ) as mock_react:
            result = react_ready_ei._execute_logic(state)

        # Should have fallen through to react_step
        assert mock_react.call_count == 2
        assert result["task_is_complete"] is False

    def test_artifact_empty_falls_through(self, react_ready_ei):
        """Declared artifact exists but is empty → falls through."""
        react_ready_ei.set_produces_artifacts({"web_builder": ["html_document.html"]})

        state = {
            "artifacts": {
                "user_request": "Build a dashboard",
                "html_document.html": "",
            },
            "routing_history": ["web_builder"],
        }

        with patch(
            "app.src.specialists.exit_interview_specialist.call_react_step",
            side_effect=[
                _make_react_step_tool_call("list_artifacts", {}),
                _make_react_step_done(False, "Empty HTML", missing_elements="Content missing"),
            ],
        ) as mock_react:
            result = react_ready_ei._execute_logic(state)

        assert mock_react.call_count == 2

    def test_no_mapping_for_specialist_falls_through(self, react_ready_ei):
        """Specialist has no produces_artifacts declaration → falls through."""
        react_ready_ei.set_produces_artifacts({"web_builder": ["html_document.html"]})

        state = {
            "artifacts": {
                "user_request": "Sort files",
            },
            "routing_history": ["project_director"],
        }

        with patch(
            "app.src.specialists.exit_interview_specialist.call_react_step",
            side_effect=[
                _make_react_step_tool_call("list_directory", {"path": "/workspace"}),
                _make_react_step_done(True, "Files sorted"),
            ],
        ) as mock_react:
            result = react_ready_ei._execute_logic(state)

        assert mock_react.call_count == 2

    def test_signal_takes_priority_over_artifact(self, exit_interview):
        """completion_signal is checked before produces_artifacts — signal wins."""
        exit_interview.set_produces_artifacts({"web_builder": ["html_document.html"]})

        state = {
            "artifacts": {
                "user_request": "Build a dashboard",
                "html_document.html": "<html>content</html>",
                "completion_signal": {
                    "status": "BLOCKED",
                    "summary": "Stagnation detected.",
                },
            },
            "routing_history": ["web_builder"],
        }

        result = exit_interview._execute_logic(state)

        # Signal path should win — BLOCKED aborts
        assert result["task_is_complete"] is True
        assert "termination_reason" in result["scratchpad"]
