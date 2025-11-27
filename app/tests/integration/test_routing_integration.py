# app/tests/integration/test_routing_integration.py
"""
Integration tests for routing behavior with real specialists.

Tests critical routing scenarios that unit tests can't catch:
- Specialist dependency requirements (web_builder → systems_architect)
- Triage advisory suggestions (non-blocking)
- Loop detection when dependencies aren't satisfied
- Router ignoring invalid recommendations

These tests use the real graph with real specialists to verify
end-to-end routing behavior.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.xfail(reason="Requires MCP migration (Task 2.8). Router uses LLM routing instead of deterministic dependency resolution. Will pass after web_builder uses McpClient for synchronous system_plan generation.")
def test_specialist_dependency_routing(initialized_app):
    """
    Verifies specialist dependency requirements are treated as CRITICAL, not advisory.

    Scenario:
    - User requests web UI modification with attached file
    - Router → web_builder
    - web_builder: "Cannot proceed without 'system_plan' from systems_architect"
    - Router sees CRITICAL DEPENDENCY REQUIREMENT (not advisory)
    - Router → systems_architect (satisfies dependency)
    - systems_architect creates system_plan
    - Router → web_builder (now has required artifact)
    - web_builder succeeds

    This test catches the bug where dependency requirements were treated as
    optional suggestions, causing router → specialist → router → specialist loops.
    """
    app = initialized_app

    with TestClient(app) as client:
        # Simulate user uploading code file and requesting modification
        payload = {
            "input_prompt": "Rewrite this Gradio app with a dark theme",
            "text_to_process": "import gradio as gr\ndef greet(name):\n    return f'Hello {name}'\ngr.Interface(fn=greet, inputs='text', outputs='text').launch()",
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # Verify no error occurred
        assert final_state.get("error_report") is None, f"Workflow failed with error: {final_state.get('error_report')}"

        # Verify routing history shows proper dependency resolution
        routing_history = final_state.get("routing_history", [])

        # Should see systems_architect run BEFORE second web_builder invocation
        # Acceptable patterns:
        # 1. [..., web_builder, systems_architect, web_builder, ...]
        # 2. [..., systems_architect, web_builder, ...]
        web_builder_indices = [i for i, spec in enumerate(routing_history) if spec == "web_builder"]
        systems_architect_indices = [i for i, spec in enumerate(routing_history) if spec == "systems_architect"]

        if len(web_builder_indices) > 1:
            # If web_builder ran multiple times, systems_architect should be between the first two
            first_web_builder = web_builder_indices[0]
            second_web_builder = web_builder_indices[1]
            assert any(first_web_builder < sa < second_web_builder for sa in systems_architect_indices), (
                f"systems_architect should run between web_builder invocations. "
                f"Routing history: {routing_history}"
            )

        # Verify no unproductive loop (web_builder should not repeat 3+ times consecutively)
        for i in range(len(routing_history) - 2):
            if (routing_history[i] == "web_builder" and
                routing_history[i+1] == "web_builder" and
                routing_history[i+2] == "web_builder"):
                pytest.fail(
                    f"Unproductive loop detected: web_builder repeated 3 times. "
                    f"Routing history: {routing_history}"
                )

        # Verify workflow completed successfully
        assert final_state.get("task_is_complete") is not False, "Workflow should complete successfully"


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


@pytest.mark.integration
def test_loop_detection_when_dependency_unsatisfied(initialized_app):
    """
    Verifies loop detection kicks in if specialist dependencies can't be satisfied.

    Scenario (hypothetical edge case):
    - Specialist A requires artifact from Specialist B
    - Specialist B is unavailable or broken
    - Router keeps trying Specialist A
    - Loop detection halts after 3 cycles
    - EndSpecialist generates report with termination reason

    This is a negative test - we want loop detection to catch pathological cases.

    NOTE: This test is harder to create without artificially breaking a specialist.
    Marking as xfail for now, but documents the expected behavior.
    """
    pytest.xfail("Requires artificially breaking a specialist to trigger unsatisfiable dependency")


@pytest.mark.integration
@pytest.mark.xfail(reason="Requires MCP migration (Task 2.8). Same dependency routing issue as test_specialist_dependency_routing.")
def test_file_upload_routing_success(initialized_app):
    """
    End-to-end test for the original bug scenario that motivated ADR-CORE-011.

    Scenario:
    - User uploads file with code
    - User requests modification (e.g., "Rewrite this with dark theme")
    - Triage may or may not recommend correct specialist
    - Router should choose web_builder (even if triage doesn't recommend it)
    - If web_builder needs system_plan, it should get systems_architect
    - Workflow completes successfully with modified code artifact

    This is the regression test for the file attachment investigation issue.
    """
    app = initialized_app

    with TestClient(app) as client:
        payload = {
            "input_prompt": "Check out this Gradio lassi app. Fix up the colors a little bit and gamify it a few more levels.",
            "text_to_process": """import gradio as gr

def calculate_bmi(weight, height):
    bmi = weight / (height ** 2)
    return f"Your BMI is: {bmi:.2f}"

gr.Interface(
    fn=calculate_bmi,
    inputs=[
        gr.Number(label="Weight (kg)"),
        gr.Number(label="Height (m)")
    ],
    outputs="text",
    title="BMI Calculator"
).launch()""",
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # Verify no error report
        assert final_state.get("error_report") is None, (
            f"File upload routing failed. Error: {final_state.get('error_report')}"
        )

        # Verify web_builder was involved (since this is web UI modification)
        routing_history = final_state.get("routing_history", [])
        assert "web_builder" in routing_history or "systems_architect" in routing_history, (
            f"Expected web_builder or systems_architect in routing history. "
            f"Got: {routing_history}"
        )

        # Verify no default_responder fallback (would indicate routing failure)
        assert "default_responder_specialist" not in routing_history, (
            "Should not fall back to default_responder for web UI modification task"
        )

        # Verify workflow completed
        assert final_state.get("task_is_complete") is not False


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


@pytest.mark.integration
@pytest.mark.xfail(reason="LLM-dependent: routing decisions vary between models, local models may not follow expected triage→facilitator→chat flow")
def test_context_aware_routing_prevents_loop(initialized_app):
    """
    End-to-end test verifying context-aware routing prevents infinite loop.

    Scenario (regression test for router loop bug):
    - User sends research query
    - Router → triage_architect (analyzes request)
    - Router → facilitator_specialist (executes context gathering)
    - facilitator_specialist creates gathered_context artifact
    - Router sees gathered_context → excludes triage/facilitator from menu
    - Router → chat_specialist or researcher_specialist (NOT back to triage)
    - Workflow completes successfully

    BEFORE FIX:
    - User → Triage → Facilitator → Router → Triage → [LOOP DETECTION ERROR]

    AFTER FIX:
    - User → Triage → Facilitator → Router → Chat/Researcher → End [SUCCESS]

    This test verifies the fix in router_specialist.py:_get_available_specialists()
    that excludes planning specialists when gathered_context artifact exists.

    NOTE: This test depends on LLM routing decisions and may fail with local models
    that don't follow the expected routing pattern.
    """
    app = initialized_app

    with TestClient(app) as client:
        # Research query that triggers triage → facilitator flow
        payload = {
            "input_prompt": "Research: winter weather patterns in Pueblo, CO",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result["final_output"]

        # CRITICAL: Verify no loop detection error
        scratchpad = final_state.get("scratchpad", {})
        assert scratchpad.get("termination_reason") is None, (
            f"Workflow should not be halted by loop detection. "
            f"Termination reason: {scratchpad.get('termination_reason')}"
        )

        # Verify no error report
        assert final_state.get("error_report") is None, (
            f"Workflow should complete without errors. Error: {final_state.get('error_report')}"
        )

        # Verify routing history shows correct flow
        routing_history = final_state.get("routing_history", [])

        # Should have triage and facilitator in history
        assert "triage_architect" in routing_history, (
            f"Expected triage_architect in routing history. Got: {routing_history}"
        )
        assert "facilitator_specialist" in routing_history, (
            f"Expected facilitator_specialist in routing history. Got: {routing_history}"
        )

        # CRITICAL: After facilitator runs, should NOT route back to triage_architect
        facilitator_indices = [i for i, spec in enumerate(routing_history) if spec == "facilitator_specialist"]
        if facilitator_indices:
            last_facilitator_idx = facilitator_indices[-1]
            # Check all specialists after last facilitator execution
            specialists_after_facilitator = routing_history[last_facilitator_idx + 1:]

            # Filter out router and check_task_completion (those are orchestration nodes)
            actual_specialists_after = [
                s for s in specialists_after_facilitator
                if s not in ["router_specialist", "check_task_completion"]
            ]

            # CRITICAL: triage_architect should NOT appear after facilitator completed
            assert "triage_architect" not in actual_specialists_after, (
                f"Router should NOT route back to triage_architect after context gathering complete. "
                f"Routing history: {routing_history}"
            )

            # CRITICAL: facilitator_specialist should NOT appear again after completing
            assert "facilitator_specialist" not in actual_specialists_after, (
                f"Router should NOT route back to facilitator_specialist after context gathering complete. "
                f"Routing history: {routing_history}"
            )

        # Verify workflow completed successfully
        assert final_state.get("task_is_complete") is not False, (
            "Workflow should complete successfully"
        )

        # Verify no unproductive loop patterns (same specialist 3+ times consecutively)
        for i in range(len(routing_history) - 2):
            if (routing_history[i] == routing_history[i+1] == routing_history[i+2] and
                routing_history[i] not in ["router_specialist", "check_task_completion"]):
                pytest.fail(
                    f"Unproductive loop detected: {routing_history[i]} repeated 3 times consecutively. "
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
        "tool_calls": [{"name": "Route", "args": {"next_specialist": ["chat_specialist"]}}]
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
        "tool_calls": [{"name": "Route", "args": {"next_specialist": ["chat_specialist"]}}]
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
