import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from app.src.specialists.critic_specialist import CriticSpecialist, BaseCritiqueStrategy
from app.src.specialists.schemas import StatusEnum, SpecialistOutput
# Assuming CritiqueOutput and Critique are Pydantic models from app.src.strategies.critique.schemas
# Since they are not provided in context, we'll create simple mocks that mimic their structure.

class MockCritique(BaseModel):
    overall_assessment: str
    decision: str
    points_for_improvement: list
    positive_feedback: list

@pytest.fixture
def mock_critique_strategy():
    """Mock for BaseCritiqueStrategy."""
    mock_strategy = MagicMock(spec=BaseCritiqueStrategy)
    return mock_strategy

@pytest.fixture
def critic_specialist(initialized_specialist_factory, mock_critique_strategy):
    """Fixture for an initialized CriticSpecialist."""
    # The CriticSpecialist requires its strategy at initialization time.
    # We bypass the factory here and instantiate it directly with the mock strategy.
    # This is a valid exception to the "always use the factory" rule for specialists
    # with complex, non-serializable dependencies.
    return CriticSpecialist(
        specialist_name="critic_specialist",
        specialist_config={"revision_target": "web_builder"},
        critique_strategy=mock_critique_strategy,
    )

def test_critic_specialist_accepts_and_completes_task(critic_specialist, mock_critique_strategy):
    """Tests that the specialist accepts the work and signals task completion."""
    # Arrange
    mock_critique = MockCritique(
        overall_assessment="Looks good.",
        decision="ACCEPT",
        points_for_improvement=[],
        positive_feedback=["Well done!"]
    )
    mock_critique_output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="Critique generated.", payload=mock_critique)
    mock_critique_strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)

    # Assert
    mock_critique_strategy.critique.assert_called_once_with(initial_state)
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "Critique complete. Decision: ACCEPT" in result_state["messages"][0].content
    assert "artifacts" in result_state
    assert "critique.md" in result_state["artifacts"]
    assert "**Overall Assessment:**\nLooks good." in result_state["artifacts"]["critique.md"]
    assert "scratchpad" in result_state
    assert result_state["scratchpad"]["critique_decision"] == "ACCEPT"
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state

def test_critic_specialist_revises_and_recommends_target(critic_specialist, mock_critique_strategy):
    """Tests that the specialist recommends revision and a target specialist."""
    # Arrange
    mock_critique = MockCritique(
        overall_assessment="Needs improvement.",
        decision="REVISE",
        points_for_improvement=["Fix this.", "Fix that."],
        positive_feedback=[]
    )
    mock_critique_output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="Revisions needed.", payload=mock_critique)
    mock_critique_strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)

    # Assert
    mock_critique_strategy.critique.assert_called_once_with(initial_state)
    assert "Critique complete. Decision: REVISE" in result_state["messages"][0].content
    assert "**Points for Improvement:**\n- Fix this.\n- Fix that." in result_state["artifacts"]["critique.md"]
    assert result_state["scratchpad"]["critique_decision"] == "REVISE"
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["web_builder"]
    assert "task_is_complete" not in result_state # Should not be set to True

def test_critic_specialist_handles_strategy_failure(critic_specialist, mock_critique_strategy):
    """Tests that the specialist handles unrecoverable failure from its strategy."""
    # Arrange
    mock_critique_output = SpecialistOutput(status=StatusEnum.FAILURE, rationale="Strategy failed.")
    mock_critique_strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)

    # Assert
    mock_critique_strategy.critique.assert_called_once_with(initial_state)
    assert "error" in result_state
    assert "critique strategy encountered an unrecoverable error: Strategy failed." in result_state["error"]
    assert "messages" in result_state
    assert "FATAL ERROR" in result_state["messages"][0].content
    assert "artifacts" in result_state
    assert "FATAL ERROR" in result_state["artifacts"]["critique.md"]
    assert "recommended_specialists" not in result_state
    assert "task_is_complete" not in result_state