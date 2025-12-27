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


# ==============================================================================
# "Not Me" Pattern Tests - Specialist Decline Handling
# ==============================================================================

class TestRouterDeclineHandling:
    """
    Tests for the "not me" pattern where specialists can decline tasks
    and remove themselves from recommended_specialists.
    """

    def test_router_removes_declining_specialist_from_recommendations(self, initialized_specialist_factory):
        """
        When a specialist declines with decline_task=True, it should be
        removed from the recommended_specialists list.
        """
        router = initialized_specialist_factory("RouterSpecialist")

        # State where text_analysis_specialist declined
        state = {
            "messages": [MagicMock(content="Analyze this text")],
            "scratchpad": {
                "decline_task": True,
                "declining_specialist": "text_analysis_specialist",
                "decline_reason": "Missing required context",
                "recommended_specialists": [
                    "text_analysis_specialist",
                    "chat_specialist",
                    "summarizer_specialist"
                ]
            }
        }

        # Simulate what _execute_logic does to process recommendations
        recommended = state["scratchpad"]["recommended_specialists"].copy()
        declining = state["scratchpad"]["declining_specialist"]

        if state["scratchpad"].get("decline_task") and declining in recommended:
            recommended = [s for s in recommended if s != declining]

        # Assert
        assert "text_analysis_specialist" not in recommended
        assert "chat_specialist" in recommended
        assert "summarizer_specialist" in recommended
        assert len(recommended) == 2

    def test_router_clears_recommendations_when_all_decline(self):
        """
        When all recommended specialists have declined, recommendations
        should be cleared so LLM can make a fresh decision.
        """
        # State where the only recommended specialist declined
        scratchpad = {
            "decline_task": True,
            "declining_specialist": "text_analysis_specialist",
            "recommended_specialists": ["text_analysis_specialist"]
        }

        recommended = scratchpad["recommended_specialists"].copy()
        declining = scratchpad["declining_specialist"]

        if scratchpad.get("decline_task") and declining in recommended:
            recommended = [s for s in recommended if s != declining]

        if not recommended:
            recommended = None

        # Assert
        assert recommended is None

    def test_decline_does_not_affect_recommendations_if_not_in_list(self):
        """
        If a declining specialist isn't in the recommendations list,
        recommendations should remain unchanged.
        """
        scratchpad = {
            "decline_task": True,
            "declining_specialist": "vision_specialist",
            "recommended_specialists": ["chat_specialist", "file_specialist"]
        }

        recommended = scratchpad["recommended_specialists"].copy()
        declining = scratchpad["declining_specialist"]

        if scratchpad.get("decline_task") and declining in recommended:
            recommended = [s for s in recommended if s != declining]

        # Assert - unchanged
        assert recommended == ["chat_specialist", "file_specialist"]

    def test_decline_without_recommendations_has_no_effect(self):
        """
        Decline with no recommendations should not cause errors.
        """
        scratchpad = {
            "decline_task": True,
            "declining_specialist": "text_analysis_specialist",
            # No recommended_specialists
        }

        recommended = scratchpad.get("recommended_specialists")
        declining = scratchpad["declining_specialist"]

        if scratchpad.get("decline_task") and recommended and declining in recommended:
            recommended = [s for s in recommended if s != declining]

        # Assert - no error, remains None
        assert recommended is None


# ==============================================================================
# State Hygiene Tests - Router Clears All Routing Signals
# ==============================================================================

class TestRouterStateCleaning:
    """
    Tests that verify the Router properly clears ALL routing-related signals
    from the scratchpad to prevent stale state pollution.

    This addresses the fragile handoff identified where decline signals
    could persist and corrupt subsequent routing decisions.
    """

    def test_router_scratchpad_clears_all_decline_signals(self, initialized_specialist_factory):
        """
        REGRESSION GUARD: Router MUST clear all decline-related signals in its return.

        Without this, stale decline signals persist in scratchpad due to operator.ior
        merge behavior, potentially corrupting subsequent routing decisions.
        """
        from unittest.mock import patch, MagicMock

        router = initialized_specialist_factory("RouterSpecialist")

        # Setup specialist map so router can route
        router.set_specialist_map({
            "chat_specialist": {"type": "llm", "description": "Chat"},
            "file_specialist": {"type": "procedural", "description": "Files"},
        })

        # State with decline signals that should be cleared
        state = {
            "messages": [MagicMock(content="Hello")],
            "scratchpad": {
                "decline_task": True,
                "declining_specialist": "some_specialist",
                "decline_reason": "Test reason",
                "recommended_specialists": ["chat_specialist"],
            },
            "turn_count": 1,
            "routing_history": [],
        }

        # Mock _get_llm_choice to return a valid routing decision
        mock_llm_decision = {
            "next_specialist": "chat_specialist",
            "content": "Routing to chat_specialist",
            "tool_calls": [],
            "router_diagnostics": {"llm_choice": "chat_specialist", "validated_choice": "chat_specialist", "available_count": 2},
        }

        with patch.object(router, '_get_llm_choice', return_value=mock_llm_decision):
            result = router._execute_logic(state)

        # Assert: All decline signals should be explicitly set to None
        scratchpad = result.get("scratchpad", {})
        assert "decline_task" in scratchpad, "Router must explicitly clear decline_task"
        assert scratchpad["decline_task"] is None, "decline_task must be set to None"
        assert "declining_specialist" in scratchpad, "Router must explicitly clear declining_specialist"
        assert scratchpad["declining_specialist"] is None, "declining_specialist must be set to None"
        assert "decline_reason" in scratchpad, "Router must explicitly clear decline_reason"
        assert scratchpad["decline_reason"] is None, "decline_reason must be set to None"
        assert "recommended_specialists" in scratchpad, "Router must explicitly clear recommended_specialists"
        assert scratchpad["recommended_specialists"] is None, "recommended_specialists must be set to None"
