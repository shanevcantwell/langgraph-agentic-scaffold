# app/tests/unit/test_clarification_workflow.py

from unittest.mock import MagicMock
import pytest
from langchain_core.messages import AIMessage

from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.end_specialist import EndSpecialist
from app.src.enums import CoreSpecialist
from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType

@pytest.fixture
def orchestrator_instance():
    """Provides a GraphOrchestrator instance for testing."""
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {}
    orchestrator = GraphOrchestrator(config, specialists)
    return orchestrator

def test_check_triage_outcome_routes_to_end_on_ask_user(orchestrator_instance):
    """
    Tests that check_triage_outcome routes directly to EndSpecialist
    when the ContextPlan contains an 'ask_user' action.
    """
    # Arrange
    plan = ContextPlan(
        reasoning="Need clarification",
        actions=[
            ContextAction(
                type=ContextActionType.ASK_USER,
                target="Which file?",
                description="Ambiguous request"
            )
        ]
    )
    
    state = {
        "artifacts": {
            "context_plan": plan.model_dump()
        }
    }

    # Act
    result = orchestrator_instance.check_triage_outcome(state)

    # Assert
    assert result == CoreSpecialist.END.value

def test_check_triage_outcome_routes_to_facilitator_on_normal_actions(orchestrator_instance):
    """
    Tests that check_triage_outcome routes to Facilitator for normal actions.
    """
    # Arrange
    plan = ContextPlan(
        reasoning="Need research",
        actions=[
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="LangGraph docs",
                description="Find docs"
            )
        ]
    )
    
    state = {
        "artifacts": {
            "context_plan": plan.model_dump()
        }
    }

    # Act
    result = orchestrator_instance.check_triage_outcome(state)

    # Assert
    assert result == "facilitator_specialist"

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

    plan = ContextPlan(
        reasoning="Need clarification",
        actions=[
            ContextAction(
                type=ContextActionType.ASK_USER,
                target="Which file do you mean?",
                description="Ambiguous"
            ),
            ContextAction(
                type=ContextActionType.ASK_USER,
                target="Is this for production?",
                description="Context needed"
            )
        ]
    )
    
    state = {
        "artifacts": {
            "context_plan": plan.model_dump()
        },
        "messages": [],
        "scratchpad": {}
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

