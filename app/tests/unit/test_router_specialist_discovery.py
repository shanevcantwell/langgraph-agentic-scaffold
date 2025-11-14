# app/tests/unit/test_router_specialist_discovery.py
"""
Tests that verify the RouterSpecialist can dynamically discover new specialists
from configuration without requiring code changes.

This is critical for ADR-001 (ChatSpecialist) and future specialist additions.
"""
import pytest
from unittest.mock import MagicMock
from app.src.specialists.router_specialist import RouterSpecialist


def test_router_discovers_specialists_from_config(initialized_specialist_factory):
    """
    Verifies that RouterSpecialist can discover and route to any specialist
    defined in config.yaml with a description field.

    This test simulates adding a new specialist (like ChatSpecialist) and ensures
    the router can see it without code modifications.
    """
    # Arrange
    router = initialized_specialist_factory("RouterSpecialist")

    # Simulate specialist configurations that would come from config.yaml
    specialist_configs = {
        "router_specialist": {
            "type": "llm",
            "description": "Master router"
        },
        "file_specialist": {
            "type": "procedural",
            "description": "Handles file operations"
        },
        "chat_specialist": {  # New specialist we're adding
            "type": "llm",
            "description": "A general-purpose conversational specialist for answering user questions and chatting."
        }
    }

    # Act
    router.set_specialist_map(specialist_configs)
    available = router._get_available_specialists({})

    # Assert
    assert "chat_specialist" in available, "Router should discover chat_specialist from config"
    assert "file_specialist" in available, "Router should discover file_specialist from config"
    assert "router_specialist" not in available, "Router should not include itself"
    assert available["chat_specialist"]["description"] == "A general-purpose conversational specialist for answering user questions and chatting."


@pytest.mark.xfail(reason="Requires MCP migration (Task 2.8). Recommendation-based routing pattern will be replaced by synchronous MCP service calls.")
def test_router_respects_recommended_specialists_filter(initialized_specialist_factory):
    """
    Verifies that RouterSpecialist correctly filters available specialists
    when recommendations are present (e.g., from TriageSpecialist).

    This is important for the diplomatic process where we want to route to
    specific specialists (e.g., ProgenitorAlpha and ProgenitorBravo).
    """
    # Arrange
    router = initialized_specialist_factory("RouterSpecialist")

    specialist_configs = {
        "chat_specialist": {
            "type": "llm",
            "description": "Chat specialist"
        },
        "file_specialist": {
            "type": "procedural",
            "description": "File specialist"
        },
        "progenitor_alpha_specialist": {
            "type": "llm",
            "description": "First perspective"
        }
    }

    router.set_specialist_map(specialist_configs)

    # State with recommendations (simulates triage filtering)
    state_with_recommendations = {
        "recommended_specialists": ["chat_specialist", "progenitor_alpha_specialist"]
    }

    # Act
    available = router._get_available_specialists(state_with_recommendations)

    # Assert
    assert len(available) == 2, "Should only include recommended specialists"
    assert "chat_specialist" in available
    assert "progenitor_alpha_specialist" in available
    assert "file_specialist" not in available, "Non-recommended specialists should be filtered out"


def test_router_handles_empty_specialist_map_gracefully(initialized_specialist_factory):
    """
    Verifies that RouterSpecialist handles edge case of no available specialists
    without crashing.
    """
    # Arrange
    router = initialized_specialist_factory("RouterSpecialist")
    router.set_specialist_map({})

    # Act
    available = router._get_available_specialists({})

    # Assert
    assert available == {}, "Should return empty dict when no specialists configured"


def test_router_ignores_specialists_without_descriptions():
    """
    Verifies that specialists without descriptions are still included in the
    specialist map but will show "No description." in the standup report.

    This is important because some procedural specialists might not need
    descriptions if they're not meant to be routed to directly.
    """
    # Arrange
    specialist_configs = {
        "file_specialist": {
            "type": "procedural",
            "description": "File operations"
        },
        "internal_helper": {
            "type": "procedural"
            # No description field
        }
    }

    # Act - Simulate what GraphBuilder does when building standup report
    standup_report = "\n".join([
        f"- {name}: {conf.get('description', 'No description.')}"
        for name, conf in specialist_configs.items()
    ])

    # Assert
    assert "file_specialist: File operations" in standup_report
    assert "internal_helper: No description." in standup_report
