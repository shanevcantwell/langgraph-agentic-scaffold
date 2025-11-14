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
