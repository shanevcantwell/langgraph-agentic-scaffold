import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel
from app.src.specialists.critic_specialist import CriticSpecialist, BaseCritiqueStrategy
from app.src.specialists.schemas import StatusEnum, SpecialistOutput
from app.src.strategies.critique.llm_strategy import LLMCritiqueStrategy
# Assuming Critique is a Pydantic model from app.src.specialists.schemas
# Since they are not provided in context, we'll create simple mocks that mimic their structure.

class MockCritique(BaseModel):
    overall_assessment: str
    decision: str
    points_for_improvement: list
    positive_feedback: list

@pytest.fixture
def critic_specialist(initialized_specialist_factory):
    """Fixture for an initialized CriticSpecialist."""
    # Use the factory, which now correctly simulates the GraphBuilder's
    # logic for creating the critic and its internal LLM-based strategy.
    specialist = initialized_specialist_factory(
        "CriticSpecialist",
        config_override={"revision_target": "web_builder"}
    )
    # For testing, we can mock the `critique` method on the *actual* strategy instance.
    specialist.strategy.critique = MagicMock()
    return specialist

def test_critic_specialist_accepts_and_completes_task(critic_specialist):
    """Tests that the specialist accepts the work and signals task completion."""
    # Arrange
    mock_critique = MockCritique(
        overall_assessment="Looks good.",
        decision="ACCEPT",
        points_for_improvement=[],
        positive_feedback=["Well done!"]
    )
    mock_critique_output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="Critique generated.", payload=mock_critique)
    critic_specialist.strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)

    # Assert
    critic_specialist.strategy.critique.assert_called_once_with(initial_state)
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
    assert "routing_history" in result_state
    assert result_state["routing_history"] == ["critic_specialist"]

def test_critic_specialist_revises_and_recommends_target(critic_specialist):
    """Tests that the specialist recommends revision and a target specialist."""
    # Arrange
    mock_critique = MockCritique(
        overall_assessment="Needs improvement.",
        decision="REVISE",
        points_for_improvement=["Fix this.", "Fix that."],
        positive_feedback=[]
    )
    mock_critique_output = SpecialistOutput(status=StatusEnum.SUCCESS, rationale="Revisions needed.", payload=mock_critique)
    critic_specialist.strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)

    # Assert
    critic_specialist.strategy.critique.assert_called_once_with(initial_state)
    assert "Critique complete. Decision: REVISE" in result_state["messages"][0].content
    assert "**Points for Improvement:**\n- Fix this.\n- Fix that." in result_state["artifacts"]["critique.md"]
    assert result_state["scratchpad"]["critique_decision"] == "REVISE"
    assert "recommended_specialists" in result_state
    assert result_state["recommended_specialists"] == ["web_builder"]
    assert "task_is_complete" not in result_state # Should not be set to True
    assert "routing_history" in result_state
    assert result_state["routing_history"] == ["critic_specialist"]

def test_critic_specialist_handles_strategy_failure(critic_specialist):
    """Tests that the specialist handles unrecoverable failure from its strategy."""
    # Arrange
    mock_critique_output = SpecialistOutput(status=StatusEnum.FAILURE, rationale="Strategy failed.", payload=None)
    critic_specialist.strategy.critique.return_value = mock_critique_output

    initial_state = {"messages": [HumanMessage(content="Here's some work.")]}

    # Act
    result_state = critic_specialist._execute_logic(initial_state)
    # Assert
    critic_specialist.strategy.critique.assert_called_once_with(initial_state)
    assert "error" in result_state
    assert "unrecoverable error" in result_state["error"]