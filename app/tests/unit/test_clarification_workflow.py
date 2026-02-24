# app/tests/unit/test_clarification_workflow.py

from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage

from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.end_specialist import EndSpecialist
from app.src.enums import CoreSpecialist

@pytest.fixture
def orchestrator_instance():
    """Provides a GraphOrchestrator instance for testing."""
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {}
    orchestrator = GraphOrchestrator(config, specialists)
    return orchestrator

def test_check_triage_outcome_rejects_ask_user_only_plan(orchestrator_instance):
    """
    #179: Ask-user-only plan = underspecified prompt. Routes to EndSpecialist
    which formats the questions as a rejection message in final_user_response.
    No in-graph interrupt — reject with cause.
    """
    # Arrange
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "ask_user", "target": "Which file?",
                 "description": "Ambiguous request"}
            ],
            "triage_reasoning": "Need clarification",
        }
    }

    # Act
    result = orchestrator_instance.check_triage_outcome(state)

    # Assert - ask_user-only routes to EndSpecialist (reject with cause)
    assert result == CoreSpecialist.END.value

def test_check_triage_outcome_routes_to_sa_on_normal_actions(orchestrator_instance):
    """
    Tests that check_triage_outcome routes to SystemsArchitect for normal
    (non-ask_user) actions. SA plans before Facilitator assembles context.
    """
    # Arrange
    state = {
        "scratchpad": {
            "triage_actions": [
                {"type": "research", "target": "LangGraph docs",
                 "description": "Find docs"}
            ],
            "triage_reasoning": "Need research",
        }
    }

    # Act
    result = orchestrator_instance.check_triage_outcome(state)

    # Assert — Triage PASS routes to SA (not Facilitator)
    assert result == "systems_architect"

# =============================================================================
# Issue #217: SA Fail-Fast — check_sa_outcome
# =============================================================================

def test_sa_outcome_routes_to_facilitator_when_task_plan_exists(orchestrator_instance):
    """
    #217: When SA successfully produces a task_plan artifact,
    check_sa_outcome routes to facilitator_specialist.
    """
    state = {
        "artifacts": {
            "task_plan": {
                "plan_summary": "Organize files by category.",
                "required_components": ["project_director"],
                "execution_steps": ["Read directory", "Create subdirs", "Move files"],
                "acceptance_criteria": "Files are sorted into category subdirectories.",
            }
        },
        "scratchpad": {},
    }

    result = orchestrator_instance.check_sa_outcome(state)
    assert result == "facilitator_specialist"


def test_sa_outcome_routes_to_end_when_task_plan_missing(orchestrator_instance):
    """
    #217: When SA fails (no task_plan in artifacts), check_sa_outcome
    routes to END and sets termination_reason for EndSpecialist.
    """
    state = {
        "artifacts": {},
        "scratchpad": {
            "error": "Specialist 'systems_architect' failed. See report for details."
        },
    }

    result = orchestrator_instance.check_sa_outcome(state)

    assert result == CoreSpecialist.END.value
    # Verify termination_reason was set for EndSpecialist
    assert "termination_reason" in state["scratchpad"]
    assert "Planning failed" in state["scratchpad"]["termination_reason"]
    assert "systems_architect" in state["scratchpad"]["termination_reason"]


def test_sa_outcome_routes_to_end_when_artifacts_empty(orchestrator_instance):
    """
    #217: When state has no artifacts at all (edge case),
    check_sa_outcome routes to END with a generic failure message.
    """
    state = {
        "scratchpad": {},
    }

    result = orchestrator_instance.check_sa_outcome(state)

    assert result == CoreSpecialist.END.value
    assert "termination_reason" in state["scratchpad"]
    assert "Unknown SA failure" in state["scratchpad"]["termination_reason"]


# =============================================================================
# SA Raw Response Preservation on Validation Failure
# =============================================================================

def test_sa_validation_failure_preserves_raw_response():
    """
    When the model returns valid JSON but SystemPlan validation fails
    (e.g., acceptance_criteria too short), _execute_logic should:
    1. Return normally (no exception) so SafeExecutor success path runs
    2. Include the raw model JSON in scratchpad.sa_raw_response
    3. NOT include task_plan in artifacts
    """
    from unittest.mock import patch
    from app.src.specialists.systems_architect import SystemsArchitect

    # Arrange: model returns valid JSON with short acceptance_criteria
    raw_response = {
        "plan_summary": "Categorize 13 files into topic subdirectories.",
        "required_components": ["filesystem access"],
        "execution_steps": ["Read files", "Create dirs", "Move files"],
        "acceptance_criteria": "..."  # Too short — validator rejects
    }

    sa = SystemsArchitect("systems_architect", {"type": "structured"})
    sa.llm_adapter = MagicMock()
    sa.llm_adapter.invoke.return_value = {"json_response": raw_response}
    sa.llm_adapter.model_name = "test-model"

    from langchain_core.messages import HumanMessage
    state = {
        "artifacts": {},
        "messages": [HumanMessage(content="Categorize files in categories_test")],
        "scratchpad": {},
    }

    # Act — should NOT raise
    result = sa._execute_logic(state)

    # Assert
    # 1. Raw response preserved in scratchpad
    assert "sa_raw_response" in result.get("scratchpad", {})
    assert result["scratchpad"]["sa_raw_response"]["acceptance_criteria"] == "..."
    assert result["scratchpad"]["sa_raw_response"]["plan_summary"] == "Categorize 13 files into topic subdirectories."

    # 2. No task_plan in artifacts (check_sa_outcome will route to END)
    assert "task_plan" not in result.get("artifacts", {})

    # 3. Message explains the failure
    assert len(result.get("messages", [])) == 1
    assert "validation failed" in result["messages"][0].content.lower()


def test_end_specialist_generates_clarification_response():
    """
    Tests that EndSpecialist generates a clarification response instead of
    synthesizing a final answer when 'ask_user' actions are present.
    """
    # Arrange
    mock_config = {"synthesis_prompt_file": "dummy.md"}
    end_specialist = EndSpecialist("end_specialist", mock_config)

    # Mock the LLM adapter to ensure it's NOT called for synthesis
    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.invoke.return_value = {"text_response": "Synthesized response"}

    # Mock the archiver to prevent actual file operations
    end_specialist.archiver = MagicMock()
    end_specialist.archiver._execute_logic.return_value = {}

    state = {
        "artifacts": {},
        "messages": [],
        "scratchpad": {
            "triage_actions": [
                {"type": "ask_user", "target": "Which file do you mean?",
                 "description": "Ambiguous"},
                {"type": "ask_user", "target": "Is this for production?",
                 "description": "Context needed"},
            ],
            "triage_reasoning": "Need clarification",
        }
    }

    # Act
    result = end_specialist._execute_logic(state)

    # Assert
    # 1. Verify the response in the state messages
    assert "messages" in state
    last_message = state["messages"][-1]
    assert isinstance(last_message, AIMessage)
    content = last_message.content
    
    # 2. Verify content contains the questions
    assert "I need some clarification" in content
    assert "- Which file do you mean?" in content
    assert "- Is this for production?" in content
    
    # 3. Verify LLM synthesis was NOT called
    end_specialist.llm_adapter.invoke.assert_not_called()

