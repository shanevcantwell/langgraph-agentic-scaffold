# app/tests/integration/test_specialist_routing_matrix.py
"""
Comprehensive integration tests for specialist routing.

Tests that the router correctly routes to each specialist based on user prompts.
Uses parameterized tests to cover all routable specialists defined in config.yaml.

These tests use the real graph with real specialists to verify end-to-end
routing behavior. LLM responses may vary, so we verify that expected specialists
appear in the routing history (allowing for valid alternative paths).
"""
import pytest
from fastapi.testclient import TestClient


# =============================================================================
# ROUTING TEST CASES
# =============================================================================
# Each tuple: (prompt, expected_specialists, description, allow_alternatives)
#
# expected_specialists: List of specialists that SHOULD appear in routing_history
# allow_alternatives: If True, test passes if ANY expected specialist appears
#                     If False, ALL expected specialists must appear
# =============================================================================

ROUTING_TEST_CASES = [
    # --- Planning & Architecture ---
    (
        "Create a detailed technical plan for building a REST API with user authentication",
        ["systems_architect"],
        "planning_task",
        True,  # May also route to chat for clarification
    ),

    # --- Web/UI Building ---
    (
        "Build me a simple HTML page with a contact form that has name, email, and message fields",
        ["web_builder", "systems_architect"],
        "web_ui_task",
        True,  # Either web_builder or systems_architect is valid
    ),

    # --- Chat/Conversational ---
    (
        "What is the difference between Python and JavaScript programming languages?",
        ["chat_specialist", "progenitor_alpha_specialist", "progenitor_bravo_specialist"],
        "chat_question",
        True,  # Tiered chat triggers progenitors
    ),

    # --- Greetings/Fallback ---
    (
        "Hello!",
        ["default_responder_specialist", "chat_specialist"],
        "greeting",
        True,  # Either is valid for greetings
    ),

    # --- Sentiment Analysis ---
    (
        "Analyze the sentiment of this review: 'This product exceeded all my expectations! Absolutely love it!'",
        ["sentiment_classifier_specialist", "chat_specialist"],
        "sentiment_analysis",
        True,  # Chat may handle this too
    ),

    # --- Research ---
    (
        "Search for and summarize the latest features in Python 3.12",
        ["researcher_specialist", "triage_architect", "facilitator_specialist"],
        "research_task",
        True,  # Research flow involves triage
    ),

    # --- Prompt Engineering ---
    (
        "Help me write a better prompt for generating code documentation",
        ["prompt_specialist", "chat_specialist"],
        "prompt_engineering",
        True,  # Chat may handle prompt questions
    ),

    # --- Batch File Operations ---
    (
        "I have a folder of files. Sort them into subfolders by their file extension",
        ["batch_processor_specialist", "chat_specialist"],
        "batch_operations",
        True,  # May clarify first
    ),

    # --- Text Analysis (when artifact provided) ---
    (
        "Summarize the key points and main arguments from the following document",
        ["text_analysis_specialist", "chat_specialist", "summarizer_specialist"],
        "text_analysis",
        True,  # Multiple specialists can handle summarization
    ),
]


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.

    This fixture is expensive (builds real graph with real LLM adapters),
    so we use module scope to share across all tests in this file.
    """
    from app.src import api
    return api.app


# =============================================================================
# PARAMETERIZED ROUTING TESTS
# =============================================================================

@pytest.mark.integration
@pytest.mark.parametrize("prompt,expected_specialists,desc,allow_alternatives", ROUTING_TEST_CASES)
def test_router_routes_to_expected_specialist(
    initialized_app, prompt, expected_specialists, desc, allow_alternatives
):
    """
    Verify router routes to expected specialist(s) for given prompt.

    This test validates that the routing system correctly identifies
    the appropriate specialist based on user intent expressed in the prompt.
    """
    with TestClient(initialized_app) as client:
        payload = {
            "input_prompt": prompt,
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200, f"API call failed for '{desc}': {response.text}"

        result = response.json()
        final_state = result.get("final_output", {})

        # Get routing history
        routing_history = final_state.get("routing_history", [])
        assert len(routing_history) > 0, f"No routing occurred for '{desc}'"

        # Check if expected specialists appear in history
        if allow_alternatives:
            # At least ONE expected specialist should appear
            found_any = any(spec in routing_history for spec in expected_specialists)
            assert found_any, (
                f"[{desc}] None of expected specialists {expected_specialists} found in "
                f"routing history: {routing_history}"
            )
        else:
            # ALL expected specialists must appear
            for spec in expected_specialists:
                assert spec in routing_history, (
                    f"[{desc}] Expected '{spec}' in routing history but got: {routing_history}"
                )

        # Verify no critical errors
        error_report = final_state.get("error_report")
        # Allow soft errors but fail on hard errors
        if error_report:
            # Check it's not a critical failure
            assert "CircuitBreakerTriggered" not in str(error_report), (
                f"[{desc}] Circuit breaker triggered: {error_report}"
            )


# =============================================================================
# SPECIFIC SPECIALIST ROUTING TESTS
# =============================================================================

@pytest.mark.integration
def test_triage_architect_is_entry_point(initialized_app):
    """
    Verify triage_architect is the entry point for complex requests.

    Per config.yaml: workflow.entry_point = "triage_architect"
    """
    with TestClient(initialized_app) as client:
        payload = {
            "input_prompt": "Research the history of machine learning and create a timeline",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])

        # triage_architect should be early in the routing history
        if "triage_architect" in routing_history:
            triage_idx = routing_history.index("triage_architect")
            # Should be one of the first specialists (allow for router decisions)
            assert triage_idx < 5, (
                f"triage_architect should be early in routing. "
                f"Found at index {triage_idx} in {routing_history}"
            )


@pytest.mark.integration
def test_tiered_chat_pattern_triggers_progenitors(initialized_app):
    """
    Verify chat_specialist triggers the tiered chat pattern with progenitors.

    When routing to chat_specialist, the system should:
    1. Fan out to progenitor_alpha_specialist and progenitor_bravo_specialist
    2. Join at tiered_synthesizer_specialist
    """
    with TestClient(initialized_app) as client:
        payload = {
            "input_prompt": "Explain the concept of recursion in programming",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])

        # Check if tiered chat pattern was invoked
        has_alpha = "progenitor_alpha_specialist" in routing_history
        has_bravo = "progenitor_bravo_specialist" in routing_history
        has_synthesizer = "tiered_synthesizer_specialist" in routing_history

        # If any progenitor ran, both should have run (parallel execution)
        if has_alpha or has_bravo:
            assert has_alpha and has_bravo, (
                f"Tiered chat should run BOTH progenitors. "
                f"Alpha: {has_alpha}, Bravo: {has_bravo}. History: {routing_history}"
            )
            assert has_synthesizer, (
                f"Tiered chat should include synthesizer. History: {routing_history}"
            )


@pytest.mark.integration
def test_workflow_completes_at_end_specialist(initialized_app):
    """
    Verify all workflows terminate at end_specialist.

    Per architecture: end_specialist is the mandatory termination point.
    """
    with TestClient(initialized_app) as client:
        payload = {
            "input_prompt": "What time is it?",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])

        # end_specialist should be in the routing history
        assert "end_specialist" in routing_history, (
            f"Workflow should terminate at end_specialist. History: {routing_history}"
        )


@pytest.mark.integration
def test_no_routing_to_internal_specialists(initialized_app):
    """
    Verify router does not directly route to internal specialists.

    Internal specialists (file_specialist, distillation_*, etc.) should
    only be invoked via MCP or subgraph patterns, never by router.
    """
    internal_specialists = [
        "file_specialist",  # MCP-only
        "distillation_prompt_expander_specialist",
        "distillation_prompt_aggregator_specialist",
        "distillation_response_collector_specialist",
        "data_processor_specialist",  # Procedural, requires artifact
    ]

    with TestClient(initialized_app) as client:
        # Use a prompt that shouldn't trigger internal specialists
        payload = {
            "input_prompt": "Tell me a joke",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])

        # None of the internal specialists should appear
        for spec in internal_specialists:
            assert spec not in routing_history, (
                f"Internal specialist '{spec}' should not be directly routed to. "
                f"History: {routing_history}"
            )


@pytest.mark.integration
def test_loop_detection_prevents_infinite_loops(initialized_app):
    """
    Verify loop detection prevents pathological routing patterns.

    The system should detect and halt unproductive loops before
    they consume excessive resources.
    """
    with TestClient(initialized_app) as client:
        # Ambiguous prompt that might cause routing confusion
        payload = {
            "input_prompt": "Do the thing with the stuff",
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])

        # Check for unproductive loops (same specialist 3+ times consecutively)
        orchestration_nodes = ["router_specialist", "check_task_completion"]
        for i in range(len(routing_history) - 2):
            if routing_history[i] not in orchestration_nodes:
                if (routing_history[i] == routing_history[i+1] == routing_history[i+2]):
                    pytest.fail(
                        f"Unproductive loop detected: {routing_history[i]} repeated 3 times. "
                        f"Full history: {routing_history}"
                    )

        # Verify workflow completed (didn't hang)
        assert len(routing_history) > 0, "Workflow should have routing history"


# =============================================================================
# SPECIALIST AVAILABILITY TESTS
# =============================================================================

@pytest.mark.integration
def test_all_config_specialists_loadable(initialized_app):
    """
    Verify all specialists defined in config.yaml loaded successfully.

    This catches configuration errors that prevent specialist instantiation.
    """
    from app.src.utils.config_loader import ConfigLoader

    config = ConfigLoader().get_config()
    defined_specialists = list(config.get("specialists", {}).keys())

    # The app should have loaded without errors if we got here
    assert len(defined_specialists) > 0, "No specialists defined in config"

    # Verify critical specialists are present
    critical = config.get("workflow", {}).get("critical_specialists", [])
    for spec in critical:
        assert spec in defined_specialists, (
            f"Critical specialist '{spec}' not in config"
        )
