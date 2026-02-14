"""
Tests for ContextPlan schema (Triage's forced-tool-call wire format).

Tests cover:
- Schema validation with actions and reasoning
- Default values (empty list for actions)
- Field requirements and validation
- Serialization for scratchpad transport
"""
import pytest
from pydantic import ValidationError

from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType


def test_context_plan_with_actions():
    """ContextPlan with populated actions list."""
    plan = ContextPlan(
        reasoning="User needs web search for weather information",
        actions=[
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="winter weather Colorado",
                description="Search for weather patterns"
            )
        ],
    )

    assert plan.reasoning == "User needs web search for weather information"
    assert len(plan.actions) == 1
    assert plan.actions[0].type == ContextActionType.RESEARCH


def test_context_plan_default_empty_actions():
    """ContextPlan defaults to empty list for actions."""
    plan = ContextPlan(
        reasoning="Simple greeting, no context needed",
    )

    assert plan.reasoning == "Simple greeting, no context needed"
    assert plan.actions == []
    assert isinstance(plan.actions, list)


def test_context_plan_validates_required_fields():
    """ContextPlan requires reasoning field."""
    with pytest.raises(ValidationError) as exc_info:
        ContextPlan(
            actions=[],
            # Missing 'reasoning' - required field
        )

    error = exc_info.value
    assert "reasoning" in str(error)


def test_context_plan_serialization():
    """ContextPlan serializes to dict for scratchpad transport."""
    plan = ContextPlan(
        reasoning="Research and explain results",
        actions=[
            ContextAction(
                type=ContextActionType.RESEARCH,
                target="LangGraph documentation",
                description="Find latest docs"
            )
        ],
    )

    serialized = plan.model_dump()

    assert "reasoning" in serialized
    assert "actions" in serialized
    assert "recommended_specialists" not in serialized  # Removed from schema
    assert len(serialized["actions"]) == 1
    assert serialized["actions"][0]["type"] == "research"


def test_context_plan_empty_actions():
    """ContextPlan with no actions (simple request, no prep needed)."""
    plan = ContextPlan(
        reasoning="Simple greeting, no context needed",
        actions=[],
    )

    assert len(plan.actions) == 0


def test_context_plan_multiple_actions():
    """ContextPlan with multiple context-gathering actions."""
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
    )

    assert len(plan.actions) == 2
    assert plan.actions[0].type == ContextActionType.READ_FILE
    assert plan.actions[1].type == ContextActionType.RESEARCH


def test_context_plan_ask_user_action():
    """ContextPlan with ask_user action for clarification."""
    plan = ContextPlan(
        reasoning="User request is ambiguous, need clarification",
        actions=[
            ContextAction(
                type=ContextActionType.ASK_USER,
                target="What kind of website do you want?",
                description="Clarify website requirements"
            )
        ],
    )

    assert len(plan.actions) == 1
    assert plan.actions[0].type == ContextActionType.ASK_USER
    assert "website" in plan.actions[0].target


def test_context_action_strategy_optional():
    """ContextAction strategy field is optional (defaults to None)."""
    action = ContextAction(
        type=ContextActionType.RESEARCH,
        target="test query",
        description="Test search"
    )

    assert action.strategy is None

    action_with_strategy = ContextAction(
        type=ContextActionType.RESEARCH,
        target="test query",
        description="Test search",
        strategy="google"
    )

    assert action_with_strategy.strategy == "google"
