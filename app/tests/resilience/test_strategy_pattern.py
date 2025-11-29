import pytest
from app.src.interface.context_schema import ContextAction, ContextActionType

def test_context_action_supports_strategy():
    """Verify that ContextAction accepts a strategy field."""
    action = ContextAction(
        type=ContextActionType.RESEARCH,
        target="query",
        description="desc",
        strategy="google"
    )
    assert action.strategy == "google"

def test_context_action_strategy_defaults_to_none():
    """Verify that strategy is optional."""
    action = ContextAction(
        type=ContextActionType.RESEARCH,
        target="query",
        description="desc"
    )
    assert action.strategy is None
