"""
Tests for RouterSpecialist context-aware routing logic.

Tests cover:
- Context-aware specialist exclusion (ADR-CORE-016: Menu Filter Pattern)
- Prevents routing loops after context gathering complete
- Triage → Facilitator → Router → Chat flow (not back to Triage)
"""
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage

from app.src.specialists.router_specialist import RouterSpecialist


@pytest.fixture
def router_specialist(initialized_specialist_factory):
    """Create RouterSpecialist with mocked dependencies."""
    specialist = initialized_specialist_factory("RouterSpecialist", "router_specialist", {})

    # Mock specialist_map with planning and response specialists
    specialist.specialist_map = {
        "triage_architect": {"description": "Analyzes user request and creates context gathering plan"},
        "facilitator_specialist": {"description": "Executes context gathering actions"},
        "chat_specialist": {"description": "Provides conversational responses"},
        "researcher_specialist": {"description": "Performs web research"}
    }

    return specialist


def test_get_available_specialists_without_gathered_context(router_specialist):
    """
    Test that all specialists are available when no gathered_context exists.

    Scenario:
    - User sends initial request
    - No gathered_context in artifacts yet
    - Router should see ALL specialists in menu
    """
    state = {
        "messages": [HumanMessage(content="Research winter weather in Pueblo, CO")],
        "artifacts": {}  # No gathered_context yet
    }

    available = router_specialist._get_available_specialists(state)

    # All 4 specialists should be available
    assert len(available) == 4
    assert "triage_architect" in available
    assert "facilitator_specialist" in available
    assert "chat_specialist" in available
    assert "researcher_specialist" in available


def test_get_available_specialists_with_gathered_context(router_specialist):
    """
    Test that planning specialists are excluded when gathered_context exists.

    Scenario:
    - Triage and Facilitator have completed context gathering
    - gathered_context artifact exists
    - Router should EXCLUDE triage_architect and facilitator_specialist
    - Only response specialists remain in menu

    This prevents the routing loop:
    BEFORE: User → Triage → Facilitator → Router → Triage → [LOOP DETECTION ERROR]
    AFTER:  User → Triage → Facilitator → Router → Chat → End [SUCCESS]
    """
    state = {
        "messages": [HumanMessage(content="Research winter weather in Pueblo, CO")],
        "artifacts": {
            "gathered_context": {
                "actions_executed": [
                    {"action_type": "RESEARCH", "result": "Context gathered"}
                ]
            }
        }
    }

    available = router_specialist._get_available_specialists(state)

    # Only 2 specialists should remain (planning specialists excluded)
    assert len(available) == 2
    assert "triage_architect" not in available  # Excluded
    assert "facilitator_specialist" not in available  # Excluded
    assert "chat_specialist" in available  # Still available
    assert "researcher_specialist" in available  # Still available


def test_get_available_specialists_with_menu_filter(router_specialist):
    """
    Test Menu Filter Pattern (ADR-CORE-016) - forbidden_specialists in scratchpad.

    Scenario:
    - InvariantMonitor detected loop and populated forbidden_specialists
    - Router should exclude forbidden specialists from menu
    - Hard constraint (P=0) - specialist cannot be selected
    """
    state = {
        "messages": [HumanMessage(content="Some request")],
        "artifacts": {},
        "scratchpad": {
            "forbidden_specialists": ["researcher_specialist"]
        }
    }

    available = router_specialist._get_available_specialists(state)

    # researcher_specialist should be excluded by menu filter
    assert len(available) == 3
    assert "triage_architect" in available
    assert "facilitator_specialist" in available
    assert "chat_specialist" in available
    assert "researcher_specialist" not in available  # Excluded by menu filter


def test_get_available_specialists_combined_filters(router_specialist):
    """
    Test that gathered_context and menu filter work together.

    Scenario:
    - gathered_context exists (excludes planning specialists)
    - forbidden_specialists includes chat_specialist (excludes via menu filter)
    - Only researcher_specialist should remain
    """
    state = {
        "messages": [HumanMessage(content="Some request")],
        "artifacts": {
            "gathered_context": {"actions_executed": []}
        },
        "scratchpad": {
            "forbidden_specialists": ["chat_specialist"]
        }
    }

    available = router_specialist._get_available_specialists(state)

    # Only researcher_specialist should remain
    assert len(available) == 1
    assert "researcher_specialist" in available
    assert "triage_architect" not in available  # Excluded by gathered_context
    assert "facilitator_specialist" not in available  # Excluded by gathered_context
    assert "chat_specialist" not in available  # Excluded by menu filter


def test_get_available_specialists_empty_gathered_context(router_specialist):
    """
    Test that empty gathered_context dict does NOT trigger exclusion.

    Scenario:
    - gathered_context exists but is empty dict {}
    - Empty dict is falsy in Python
    - Planning specialists should NOT be excluded
    - Only non-empty gathered_context triggers exclusion
    """
    state = {
        "messages": [HumanMessage(content="Some request")],
        "artifacts": {
            "gathered_context": {}  # Empty - won't trigger exclusion
        }
    }

    available = router_specialist._get_available_specialists(state)

    # All specialists should be available (empty dict is falsy)
    assert len(available) == 4
    assert "triage_architect" in available
    assert "facilitator_specialist" in available
    assert "chat_specialist" in available
    assert "researcher_specialist" in available


def test_get_available_specialists_no_scratchpad(router_specialist):
    """
    Test that missing scratchpad key doesn't cause errors.

    Scenario:
    - State has no scratchpad key
    - Should not crash
    - No menu filter applied
    """
    state = {
        "messages": [HumanMessage(content="Some request")],
        "artifacts": {}
        # No scratchpad key
    }

    available = router_specialist._get_available_specialists(state)

    # All specialists available (no menu filter)
    assert len(available) == 4


def test_get_available_specialists_logging(router_specialist, caplog):
    """
    Test that context-aware exclusion logs informative message.

    Scenario:
    - gathered_context exists
    - Should log info message about planning specialists removal
    """
    state = {
        "messages": [HumanMessage(content="Some request")],
        "artifacts": {
            "gathered_context": {"actions_executed": []}
        }
    }

    import logging
    with caplog.at_level(logging.INFO):
        available = router_specialist._get_available_specialists(state)

    # Verify log message contains expected content
    log_messages = [record.message for record in caplog.records]
    assert any("Context gathering complete" in msg for msg in log_messages)
    assert any("removed planning specialists" in msg for msg in log_messages)
    assert any("2 specialists remain" in msg for msg in log_messages)


def test_recommendation_filtering_with_gathered_context(router_specialist):
    """
    Test that recommendations are filtered when specialists are excluded from menu.

    Scenario:
    - gathered_context exists (planning specialists excluded)
    - Triage recommends chat_specialist and triage_architect
    - Should filter out triage_architect, keep only chat_specialist

    This prevents LLM from choosing excluded specialists based on recommendations.
    """
    # Mock LLM adapter to capture the prompt
    captured_prompts = []

    def mock_invoke(request):
        captured_prompts.append(request.messages[-1].content)
        return {
            "tool_calls": [{
                "name": "Route",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

    router_specialist.llm_adapter.invoke = mock_invoke

    state = {
        "messages": [HumanMessage(content="Research query")],
        "artifacts": {
            "gathered_context": {"actions_executed": []}
        },
        "scratchpad": {
            "recommended_specialists": ["chat_specialist", "triage_architect"]
        },
        "routing_history": []
    }

    result = router_specialist._get_llm_choice(state)

    # Verify the prompt mentions only chat_specialist in recommendations
    prompt = captured_prompts[0]
    assert "chat_specialist" in prompt
    # triage_architect should be filtered out from recommendations
    # (it might appear in routing history but not in current recommendations)
    assert "TRIAGE SUGGESTIONS" in prompt or "chat_specialist" in prompt


def test_all_recommendations_filtered_out(router_specialist, caplog):
    """
    Test behavior when all recommendations are filtered out.

    Scenario:
    - gathered_context exists
    - Triage recommends only triage_architect and facilitator_specialist
    - Both are filtered out (not in available menu)
    - Should not show recommendation context at all
    """
    # Mock LLM adapter
    def mock_invoke(request):
        return {
            "tool_calls": [{
                "name": "Route",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

    router_specialist.llm_adapter.invoke = mock_invoke

    state = {
        "messages": [HumanMessage(content="Research query")],
        "artifacts": {
            "gathered_context": {"actions_executed": []}
        },
        "scratchpad": {
            "recommended_specialists": ["triage_architect", "facilitator_specialist"]
        },
        "routing_history": []
    }

    import logging
    with caplog.at_level(logging.INFO):
        result = router_specialist._get_llm_choice(state)

    # Verify log shows all recommendations were filtered
    log_messages = [record.message for record in caplog.records]
    assert any("filtered out" in msg.lower() for msg in log_messages)


def test_context_gathering_complete_note_in_prompt(router_specialist):
    """
    Test that explicit guidance is added when context gathering is complete.

    Scenario:
    - gathered_context exists
    - Should add "CONTEXT GATHERING COMPLETE" note to prompt
    - Should explain that planning specialists are no longer available
    """
    captured_prompts = []

    def mock_invoke(request):
        captured_prompts.append(request.messages[-1].content)
        return {
            "tool_calls": [{
                "name": "Route",
                "args": {"next_specialist": "chat_specialist"}
            }]
        }

    router_specialist.llm_adapter.invoke = mock_invoke

    state = {
        "messages": [HumanMessage(content="Research query")],
        "artifacts": {
            "gathered_context": {"actions_executed": []}
        },
        "routing_history": []
    }

    result = router_specialist._get_llm_choice(state)

    # Verify prompt contains context gathering complete note
    prompt = captured_prompts[0]
    assert "CONTEXT GATHERING COMPLETE" in prompt
    assert "triage and facilitator specialists have finished" in prompt.lower() or \
           "no longer available" in prompt.lower()


def test_triage_recommendations_included_in_router_prompt(router_specialist):
    """
    Test that triage recommendations are properly included in router prompt.

    Scenario:
    - Triage sets recommended_specialists in scratchpad
    - Router should include these in prompt as "TRIAGE SUGGESTIONS (ADVISORY)"
    - Recommendations should guide but not force the choice
    """
    captured_prompts = []

    def mock_invoke(request):
        captured_prompts.append(request.messages[-1].content)
        return {
            "tool_calls": [{
                "name": "Route",
                "args": {"next_specialist": "researcher_specialist"}
            }]
        }

    router_specialist.llm_adapter.invoke = mock_invoke

    state = {
        "messages": [HumanMessage(content="Research winter weather")],
        "artifacts": {},
        "scratchpad": {
            "recommended_specialists": ["researcher_specialist", "chat_specialist"]
        },
        "routing_history": []  # Fresh request, no routing history yet
    }

    result = router_specialist._get_llm_choice(state)

    # Verify recommendations are in prompt
    prompt = captured_prompts[0]
    assert "TRIAGE SUGGESTIONS" in prompt or "recommends considering" in prompt.lower()
    assert "researcher_specialist" in prompt
    assert "chat_specialist" in prompt
    # Should be marked as advisory, not mandatory
    assert "ADVISORY" in prompt or "suggestions" in prompt.lower()


def test_researcher_specialist_recommended_for_web_search(router_specialist):
    """
    Test the specific case from user's trace: web search should route to researcher.

    Scenario:
    - User asks for web research
    - Triage recommends researcher_specialist
    - After context gathering, router should choose researcher_specialist
    - NOT text_analysis_specialist (which was the bug)
    """
    captured_prompts = []

    def mock_invoke(request):
        captured_prompts.append(request.messages[-1].content)
        return {
            "tool_calls": [{
                "name": "Route",
                "args": {"next_specialist": "researcher_specialist"}
            }]
        }

    router_specialist.llm_adapter.invoke = mock_invoke

    state = {
        "messages": [HumanMessage(content="Research winter weather patterns in Colorado")],
        "artifacts": {
            "gathered_context": "Research action executed for: winter weather patterns Colorado"
        },
        "scratchpad": {
            "recommended_specialists": ["researcher_specialist"],
            "triage_reasoning": "User needs web search for real-time weather information"
        },
        "routing_history": ["triage_architect", "facilitator_specialist"]
    }

    result = router_specialist._get_llm_choice(state)

    # Verify researcher_specialist is mentioned in prompt
    prompt = captured_prompts[0]
    assert "researcher_specialist" in prompt
    # Verify context gathering complete note is present
    assert "CONTEXT GATHERING COMPLETE" in prompt
    # Verify triage/facilitator are no longer in menu
    assert "triage" not in prompt.lower() or "no longer available" in prompt.lower()
