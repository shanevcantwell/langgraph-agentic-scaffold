"""
Tests for ContextPlan schema with recommended_specialists field.

Tests cover:
- Schema validation with recommended_specialists
- Default values (empty list for recommendations)
- Field requirements and validation
"""
import pytest
from pydantic import ValidationError

from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType


def test_context_plan_with_recommended_specialists():
    """
    Test ContextPlan with recommended_specialists field populated.

    Scenario:
    - Create plan with actions and specialist recommendations
    - Verify all fields serialize correctly
    """
    plan = ContextPlan(
        reasoning="User needs web search for weather information",
        actions=[
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="winter weather Colorado",
                description="Search for weather patterns"
            )
        ],
        recommended_specialists=["researcher_specialist", "chat_specialist"]
    )

    assert plan.reasoning == "User needs web search for weather information"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == ContextActionType.RESEARCH
    assert len(plan.recommended_specialists) == 2
    assert "researcher_specialist" in plan.recommended_specialists
    assert "chat_specialist" in plan.recommended_specialists


def test_context_plan_default_empty_recommendations():
    """
    Test ContextPlan defaults to empty list for recommended_specialists.

    Scenario:
    - Create plan without specifying recommended_specialists
    - Verify it defaults to empty list (not None)
    """
    plan = ContextPlan(
        reasoning="Simple greeting, no context needed",
        actions=[]
    )

    assert plan.reasoning == "Simple greeting, no context needed"
    assert plan.actions == []
    assert plan.recommended_specialists == []  # Default empty list
    assert isinstance(plan.recommended_specialists, list)


def test_context_plan_validates_required_fields():
    """
    Test ContextPlan requires reasoning field.

    Scenario:
    - Attempt to create plan without required 'reasoning' field
    - Should raise ValidationError
    """
    with pytest.raises(ValidationError) as exc_info:
        ContextPlan(
            actions=[],
            recommended_specialists=["chat_specialist"]
            # Missing 'reasoning' - required field
        )

    error = exc_info.value
    assert "reasoning" in str(error)


def test_context_plan_single_recommendation():
    """
    Test ContextPlan with single specialist recommendation.

    Scenario:
    - Create plan recommending only one specialist
    - Common for focused tasks (e.g., file operations)
    """
    plan = ContextPlan(
        reasoning="User wants to move a file",
        actions=[
            ContextAction(
                type=ContextActionType.LIST_DIRECTORY,
                target=".",
                description="See available folders"
            )
        ],
        recommended_specialists=["file_operations_specialist"]
    )

    assert len(plan.recommended_specialists) == 1
    assert plan.recommended_specialists[0] == "file_operations_specialist"


def test_context_plan_serialization():
    """
    Test ContextPlan serializes to dict correctly (for state artifacts).

    Scenario:
    - Create plan and convert to dict using model_dump()
    - Verify all fields present in serialized form
    - This is how triage stores plan in artifacts
    """
    plan = ContextPlan(
        reasoning="Research and explain results",
        actions=[
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="LangGraph documentation",
                description="Find latest docs"
            )
        ],
        recommended_specialists=["researcher_specialist", "chat_specialist"]
    )

    serialized = plan.model_dump()

    assert "reasoning" in serialized
    assert "actions" in serialized
    assert "recommended_specialists" in serialized
    assert serialized["recommended_specialists"] == ["researcher_specialist", "chat_specialist"]
    assert len(serialized["actions"]) == 1
    assert serialized["actions"][0]["type"] == "research"


def test_context_plan_empty_actions_with_recommendations():
    """
    Test ContextPlan with no actions but with recommendations.

    Scenario:
    - Simple request (e.g., greeting) needs no context gathering
    - But still needs specialist recommendation for response
    """
    plan = ContextPlan(
        reasoning="Simple greeting, no context needed",
        actions=[],
        recommended_specialists=["chat_specialist"]
    )

    assert len(plan.actions) == 0
    assert len(plan.recommended_specialists) == 1
    assert plan.recommended_specialists[0] == "chat_specialist"


def test_context_plan_multiple_actions_with_recommendations():
    """
    Test ContextPlan with multiple actions and recommendations.

    Scenario:
    - Complex request requiring multiple context actions
    - Multiple specialists could handle the final task
    """
    plan = ContextPlan(
        reasoning="Need to read file and search for updates",
        actions=[
            ContextAction(
                type=ContextActionType.READ_FILE,
                target="README.md",
                description="Read current content"
            ),
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="latest library versions",
                description="Check for updates"
            )
        ],
        recommended_specialists=["file_operations_specialist", "text_analysis_specialist"]
    )

    assert len(plan.actions) == 2
    assert plan.actions[0].type == ContextActionType.READ_FILE
    assert plan.actions[1].type == ContextActionType.RESEARCH
    assert len(plan.recommended_specialists) == 2
