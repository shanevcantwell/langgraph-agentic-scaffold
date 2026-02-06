# app/tests/integration/test_routing_integration.py
"""
Integration tests for routing behavior with real specialists.

Tests critical routing scenarios that unit tests can't catch:
- Triage advisory suggestions (non-blocking)
- Loop detection when dependencies aren't satisfied
- Specialist decline handling ("not me" pattern)

These tests use the real graph with real specialists to verify
end-to-end routing behavior.

NOTE: Tests for MCP dependency routing (web_builder → systems_architect)
moved to GitHub Issue #10 pending MCP migration.
"""
import pytest
from fastapi.testclient import TestClient

from app.tests.conftest import assert_response_not_error


@pytest.mark.integration
def test_triage_advisory_not_restrictive(initialized_app):
    """
    Verifies triage recommendations are advisory (not restrictive).

    Scenario:
    - User sends simple chat question
    - Triage recommends chat_specialist (advisory)
    - Router sees triage suggestion but can choose differently
    - Router makes final decision based on full context

    This test verifies that router is not BLOCKED from choosing specialists
    outside triage's recommendations (ADR-CORE-011).
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "What is Python?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # Verify no error occurred
        assert final_state.get("error_report") is None

        # Verify workflow completed (router wasn't blocked by restrictive triage)
        routing_history = final_state.get("routing_history", [])
        assert len(routing_history) > 0, "Router should have made at least one routing decision"

        # Verify no unproductive loops
        assert not final_state.get("scratchpad", {}).get("termination_reason"), (
            "Workflow should not be halted by loop detection"
        )

        # Validate response content doesn't contain error indicators
        artifacts = final_state.get("artifacts", {})
        if isinstance(artifacts, dict):
            final_response = artifacts.get("final_user_response.md", "")
            if final_response:
                assert_response_not_error(final_response, "[TriageAdvisory]")


@pytest.mark.integration
@pytest.mark.skip(reason="Blocking signal enforcement deferred per ADR-CORE-009 (requires Tasks 1.4-1.6: System Invariants & Circuit Breaker)")
def test_router_respects_specialist_cannot_proceed(initialized_app):
    """
    Verifies router treats "cannot proceed" messages as blocking, not advisory.

    Scenario:
    - Specialist returns: "I cannot proceed without X artifact"
    - Sets recommended_specialists to dependency provider
    - Router sees: CRITICAL DEPENDENCY REQUIREMENT (not advisory)
    - Router MUST NOT route back to same specialist immediately
    - Router routes to dependency provider first

    This tests the core fix for the routing loop bug.
    """
    app = initialized_app

    with TestClient(app) as client:
        # Request that will trigger web_builder dependency on systems_architect
        payload = {
            "input_prompt": "Build me a recipe app with ingredient tracking",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        routing_history = final_state.get("routing_history", [])

        # If web_builder ran and requested systems_architect, verify router respected it
        for i in range(len(routing_history) - 1):
            if routing_history[i] == "web_builder":
                # Check if next non-router specialist is also web_builder
                # (would indicate router ignored dependency)
                next_specialists = [
                    s for s in routing_history[i+1:]
                    if s not in ["router_specialist", "check_task_completion"]
                ]
                if next_specialists and next_specialists[0] == "web_builder":
                    # This might be okay if systems_architect ran in between
                    # Check if systems_architect is in the routing history between the two web_builders
                    next_web_builder_idx = routing_history.index("web_builder", i+1)
                    between_specialists = routing_history[i+1:next_web_builder_idx]
                    if "systems_architect" not in between_specialists:
                        pytest.fail(
                            f"Router routed back to web_builder without satisfying dependency. "
                            f"Routing history: {routing_history}"
                        )


# ============================================================================
# "Not Me" Pattern Integration Tests - Specialist Decline Handling
# ============================================================================

@pytest.mark.integration
def test_router_removes_declining_specialist_from_routing_decision(initialized_specialist_factory):
    """
    Integration test verifying the Router's actual _get_llm_choice method
    respects the decline_task signal.

    This tests the REAL Router code path, not a manual replication of the logic.

    Scenario:
    - Specialist declined (decline_task=True in scratchpad)
    - Router's _get_llm_choice() should filter out the declining specialist
    - The declining specialist should NOT appear in the prompt to the LLM

    Key invariant: A declining specialist is removed from THIS routing decision
    but NOT permanently banned (scratchpad is transient).
    """
    from unittest.mock import MagicMock, patch
    from langchain_core.messages import HumanMessage

    router = initialized_specialist_factory("RouterSpecialist")

    # Set up specialist map with multiple specialists
    specialist_configs = {
        "chat_specialist": {
            "type": "llm",
            "description": "General chat"
        },
        "text_analysis_specialist": {
            "type": "llm",
            "description": "Text analysis"
        },
        "summarizer_specialist": {
            "type": "llm",
            "description": "Summarization"
        }
    }
    router.set_specialist_map(specialist_configs)

    # State where text_analysis_specialist has declined
    state = {
        "messages": [HumanMessage(content="Analyze this text")],
        "artifacts": {},
        "routing_history": ["triage_architect", "text_analysis_specialist"],
        "scratchpad": {
            "decline_task": True,
            "declining_specialist": "text_analysis_specialist",
            "decline_reason": "Missing required context for analysis",
            "recommended_specialists": [
                "text_analysis_specialist",
                "chat_specialist",
                "summarizer_specialist"
            ]
        }
    }

    # Mock the LLM to capture what the Router sends to it
    mock_response = {
        "json_response": {"next_specialist": ["chat_specialist"]}
    }

    with patch.object(router, 'llm_adapter') as mock_adapter:
        mock_adapter.invoke.return_value = mock_response

        # Call the actual Router method
        result = router._get_llm_choice(state)

        # Get the messages sent to the LLM
        call_args = mock_adapter.invoke.call_args
        request = call_args[0][0]  # StandardizedLLMRequest

        # Extract the full prompt content
        prompt_content = " ".join([str(m.content) for m in request.messages])

        # The key behavior: declining specialist is REMOVED from recommended list
        # It should appear in the "cannot proceed" message (explaining WHO declined)
        # But NOT in the "route to one of these" list
        if "Dependency Requirement" in prompt_content:
            dep_section = prompt_content.split("Dependency Requirement")[1]
            # The declining specialist is mentioned as the one who "cannot proceed"
            assert "text_analysis_specialist' specialist cannot proceed" in dep_section, \
                "Declining specialist should be identified as the one who cannot proceed"
            # But the recommended targets should NOT include the declining specialist
            # "from one of the following: chat_specialist, summarizer_specialist"
            assert "chat_specialist, summarizer_specialist" in dep_section or \
                   "summarizer_specialist, chat_specialist" in dep_section, \
                "Filtered recommendations should only include non-declining specialists"

        # Verify the Router chose an alternative (not the declining specialist)
        assert result["next_specialist"] == "chat_specialist", \
            "Router should route to alternative, not declining specialist"


@pytest.mark.integration
@pytest.mark.skip(reason="Requires a specialist that actually implements decline pattern. Enable when VisionSpecialist or similar uses create_decline_response().")
def test_specialist_decline_full_workflow(initialized_app):
    """
    Full end-to-end integration test for the "not me" pattern.

    This test will be enabled when a real specialist implements the
    decline pattern using create_decline_response().

    Scenario:
    1. User sends request that triggers Specialist X
    2. Specialist X determines it cannot handle task, calls create_decline_response()
    3. Router receives decline signal, removes X from recommendations
    4. Router routes to alternative specialist Y
    5. Specialist X does NOT appear again in routing_history (until next user turn)

    This test validates the FULL round-trip:
    - Specialist decline → Router handling → Alternative routing

    IMPORTANT: The decline is TEMPORARY (this turn only):
    - Scratchpad is transient
    - On next user message, X is eligible again
    """
    from fastapi.testclient import TestClient

    app = initialized_app

    with TestClient(app) as client:
        # Send a request that would trigger a specialist to decline
        # (This requires a specialist that actually implements decline)
        payload = {
            "input_prompt": "Process this image",  # VisionSpecialist might decline if no image
            "text_to_process": None,
            "image_to_process": None  # No image = VisionSpecialist should decline
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        routing_history = final_state.get("routing_history", [])

        # This test REQUIRES a decline to have occurred
        # Check scratchpad for decline evidence
        scratchpad = final_state.get("scratchpad", {})
        # Note: decline_task may be cleared after routing, but we should see evidence
        # in messages with is_decline=True

        # Find messages with decline marker
        messages = final_state.get("messages", [])
        decline_messages = [
            m for m in messages
            if isinstance(m, dict) and m.get("additional_kwargs", {}).get("is_decline")
        ]

        assert decline_messages, (
            "No specialist declined in this workflow. "
            "This test requires a specialist to implement create_decline_response(). "
            f"Routing history: {routing_history}"
        )

        # Find which specialist declined
        declining_specialist = decline_messages[0].get("name")
        assert declining_specialist, "Decline message should have specialist name"

        # After decline, the declining specialist should NOT appear again immediately
        if declining_specialist in routing_history:
            first_idx = routing_history.index(declining_specialist)
            remaining_history = routing_history[first_idx + 1:]
            actual_specialists = [
                s for s in remaining_history
                if s not in ["router_specialist", "check_task_completion"]
            ]
            assert declining_specialist not in actual_specialists[:1], (
                f"Declining specialist '{declining_specialist}' should not be immediately re-routed to. "
                f"History: {routing_history}"
            )


@pytest.mark.integration
def test_decline_signal_is_consumed_after_routing(initialized_specialist_factory):
    """
    Verifies the Router consumes (clears) the decline signal after routing.

    This ensures the decline is TEMPORARY - only for the current routing decision.
    On the next Router turn, the specialist is eligible again.

    The key behavior:
    - Router reads decline_task from scratchpad
    - Router filters out declining specialist for THIS decision
    - Router outputs scratchpad with recommended_specialists = None (consumed)
    - Next Router turn: decline_task is gone, specialist is eligible
    """
    from unittest.mock import MagicMock, patch
    from langchain_core.messages import HumanMessage

    router = initialized_specialist_factory("RouterSpecialist")

    specialist_configs = {
        "chat_specialist": {"type": "llm", "description": "Chat"},
        "text_analysis_specialist": {"type": "llm", "description": "Analysis"}
    }
    router.set_specialist_map(specialist_configs)

    state = {
        "messages": [HumanMessage(content="Hello")],
        "artifacts": {},
        "routing_history": [],
        "turn_count": 0,
        "scratchpad": {
            "decline_task": True,
            "declining_specialist": "text_analysis_specialist",
            "recommended_specialists": ["text_analysis_specialist", "chat_specialist"]
        }
    }

    mock_response = {
        "json_response": {"next_specialist": ["chat_specialist"]}
    }

    with patch.object(router, 'llm_adapter') as mock_adapter:
        mock_adapter.invoke.return_value = mock_response
        mock_adapter.model_name = "test-model"

        # Execute the full routing logic
        result = router._execute_logic(state)

        # Verify scratchpad output clears recommendations (signals consumption)
        assert "scratchpad" in result
        assert result["scratchpad"].get("recommended_specialists") is None, \
            "Router should consume (clear) recommended_specialists after routing"

        # The decline_task signal is NOT explicitly cleared by Router
        # It's cleared by the state management (scratchpad is transient)
        # This is validated by the architecture, not the Router code


# ============================================================================
# FIXTURE: Initialized FastAPI App
# ============================================================================

@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.

    This fixture is expensive (builds real graph with real LLM adapters),
    so we use module scope to share across all tests in this file.
    """
    # Import here to ensure proper initialization order
    from app.src import api

    # The app's lifespan should have already initialized the workflow_runner
    # during module import. Just return the app.
    return api.app
