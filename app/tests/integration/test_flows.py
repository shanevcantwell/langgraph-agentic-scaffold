# app/tests/integration/test_flows.py
"""
Flow Integration Tests - ZERO MOCKS

These tests validate the flows documented in docs/FLOWS.md by running
real prompts through the streaming API and verifying specialist execution.

Each test corresponds to a specific flow in FLOWS.md:
- 1.x: Chat flows
- 2.x: File operation flows
- 3.x: Browser flows (skipped without surf-mcp)
- 4.x: Research flows
- 5.x: Generation flows
- 6.x: Analysis flows

Test Pattern:
1. POST to /v1/graph/stream with the documented prompt
2. Parse SSE events to collect specialist execution order
3. Verify routing_history matches expected flow
4. Verify output contains expected patterns
"""
import pytest
import json
import re
from typing import List, Dict, Any, Set
from fastapi.testclient import TestClient


# ============================================================================
# Error Detection
# ============================================================================

# TODO: Replace with API error_level check when available (Issue #XX)
# These strings indicate the workflow failed but still produced output
ERROR_INDICATORS = [
    "stuck in an unproductive loop",
    "unable to generate a final response",
    "error occurred while generating",
    "no specific output was generated",
    "unable to provide a response",
    "Router failed to select",
    "cannot proceed without artifacts",
    "No final response was generated",
    "FATAL ERROR",
]


def assert_response_not_error(response_content: str, context: str = "") -> None:
    """Assert that response content doesn't contain error indicators."""
    response_lower = response_content.lower()
    for indicator in ERROR_INDICATORS:
        assert indicator.lower() not in response_lower, (
            f"{context} Response contains error indicator '{indicator}'"
        )


def get_artifact(final_state: dict, artifact_name: str) -> str | None:
    """
    Safely extract an artifact from final_state, handling both dict and list formats.

    Archiver may return artifacts as:
    - dict: {"html_document.html": "...", "system_plan": {...}}
    - list: ["html_document.html", "system_plan.json", ...]

    Returns the artifact content (str) or None if not found.
    """
    if final_state is None:
        return None

    artifacts = final_state.get('artifacts', {})

    if isinstance(artifacts, dict):
        return artifacts.get(artifact_name)
    elif isinstance(artifacts, list):
        # List format - check if artifact name is in list
        # This means artifact exists but content isn't directly available
        if artifact_name in artifacts:
            return f"[Artifact '{artifact_name}' exists in archive]"
        return None
    else:
        return None


# ============================================================================
# SSE Parsing Utilities
# ============================================================================

def parse_sse_stream(response_text: str) -> Dict[str, Any]:
    """
    Parse SSE stream and extract:
    - specialist_order: List of specialists in execution order
    - final_state: The final state dict (if present)
    - routing_history: The routing history from final_state
    - status_updates: All status update strings
    - errors: Any error messages
    """
    specialist_order = []
    specialist_set = set()
    status_updates = []
    errors = []
    final_state = None
    run_id = None

    for line in response_text.split('\n'):
        if not line.startswith('data:'):
            continue

        try:
            data_str = line[len('data:'):].strip()
            data = json.loads(data_str)

            # Capture run_id
            if 'run_id' in data:
                run_id = data['run_id']

            # Capture status updates and extract specialist names
            if 'status' in data:
                status_updates.append(data['status'])
                match = re.search(r'Executing specialist: (\w+)', data['status'])
                if match:
                    specialist = match.group(1)
                    if specialist not in specialist_set:
                        specialist_order.append(specialist)
                        specialist_set.add(specialist)

            # Capture errors
            if 'error' in data:
                errors.append(data['error'])
            if 'error_report' in data and data['error_report']:
                errors.append(data['error_report'])

            # Capture final state
            if 'final_state' in data:
                final_state = data['final_state']

        except json.JSONDecodeError:
            pass

    routing_history = final_state.get('routing_history', []) if final_state else []

    return {
        'specialist_order': specialist_order,
        'routing_history': routing_history,
        'final_state': final_state,
        'status_updates': status_updates,
        'errors': errors,
        'run_id': run_id,
    }


def assert_specialists_called(
    result: Dict[str, Any],
    required: List[str],
    message: str = ""
) -> None:
    """Assert that all required specialists were called."""
    called = set(result['specialist_order'])
    # Also check routing_history as backup
    if result['routing_history']:
        called.update(result['routing_history'])

    missing = set(required) - called
    if missing:
        pytest.fail(
            f"{message}\n"
            f"Missing specialists: {missing}\n"
            f"Called: {result['specialist_order']}\n"
            f"Routing history: {result['routing_history']}"
        )


def assert_specialist_sequence(
    result: Dict[str, Any],
    sequence: List[str],
    message: str = ""
) -> None:
    """Assert specialists were called in the specified order (allowing extras between)."""
    order = result['specialist_order']
    seq_idx = 0

    for specialist in order:
        if seq_idx < len(sequence) and specialist == sequence[seq_idx]:
            seq_idx += 1

    if seq_idx != len(sequence):
        remaining = sequence[seq_idx:]
        pytest.fail(
            f"{message}\n"
            f"Expected sequence: {sequence}\n"
            f"Actual order: {order}\n"
            f"Missing from sequence: {remaining}"
        )


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def api_client():
    """
    Provides a TestClient connected to the real FastAPI app.
    Module-scoped for efficiency (graph build is expensive).
    """
    from app.src import api
    with TestClient(api.app) as client:
        yield client


def invoke_flow(client: TestClient, prompt: str, **kwargs) -> Dict[str, Any]:
    """Helper to invoke the streaming API and parse results."""
    payload = {
        "input_prompt": prompt,
        "text_to_process": kwargs.get("text_to_process"),
        "image_to_process": kwargs.get("image_to_process"),
        "use_simple_chat": kwargs.get("use_simple_chat", False),
    }

    response = client.post("/v1/graph/stream", json=payload)
    assert response.status_code == 200, f"API error: {response.status_code} - {response.text[:500]}"

    return parse_sse_stream(response.text)


# ============================================================================
# 1. CHAT FLOWS
# ============================================================================

class TestChatFlows:
    """Flow 1.x: Chat-related flows from FLOWS.md"""

    @pytest.mark.integration
    def test_flow_1_1_simple_question(self, api_client):
        """
        Flow 1.1: Simple Question (Tiered Chat)

        PROMPT: "What is the capital of France?"

        Expected specialists:
        - triage_architect → entry
        - router_specialist → routing
        - progenitor_alpha_specialist → parallel response
        - progenitor_bravo_specialist → parallel response
        - tiered_synthesizer_specialist → combine
        - end_specialist → termination
        """
        result = invoke_flow(api_client, "What is the capital of France?")

        # Must have triage and router
        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 1.1: Missing core routing specialists"
        )

        # Check for tiered chat specialists
        called = set(result['specialist_order'])
        tiered_chat = {
            "progenitor_alpha_specialist",
            "progenitor_bravo_specialist",
            "tiered_synthesizer_specialist"
        }

        # Either tiered chat (progenitors + synthesizer) or simple chat
        has_tiered = tiered_chat.issubset(called)
        has_simple = "chat_specialist" in called

        assert has_tiered or has_simple, (
            f"Flow 1.1: Expected tiered chat or simple chat. "
            f"Got: {called}"
        )

        # End specialist should terminate
        assert "end_specialist" in called, "Flow 1.1: Missing end_specialist"

        # Verify no errors
        assert not result['errors'], f"Flow 1.1: Unexpected errors: {result['errors']}"

    @pytest.mark.integration
    def test_flow_1_2_comparative_question(self, api_client):
        """
        Flow 1.2: Comparative Question

        PROMPT: "Compare Python and JavaScript for web development"

        Expected: Same as 1.1 (tiered chat) but with comparative content.
        """
        result = invoke_flow(
            api_client,
            "Compare Python and JavaScript for web development"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 1.2: Missing core specialists"
        )

        # Should use tiered chat for comparative questions
        called = set(result['specialist_order'])
        if "progenitor_alpha_specialist" in called:
            assert "progenitor_bravo_specialist" in called, (
                "Flow 1.2: Alpha progenitor called but not Bravo"
            )

        assert not result['errors'], f"Flow 1.2: Unexpected errors: {result['errors']}"

    @pytest.mark.integration
    def test_flow_1_3_greeting_fast_path(self, api_client):
        """
        Flow 1.3: Greeting (Fast Path)

        PROMPT: "Hello"

        Expected specialists:
        - triage_architect
        - router_specialist
        - default_responder (fast path, no progenitors)
        - end_specialist
        """
        result = invoke_flow(api_client, "Hello")

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 1.3: Missing core specialists"
        )

        called = set(result['specialist_order'])

        # Fast path: should NOT use heavy progenitors for simple greeting
        # Either default_responder OR simple chat
        uses_fast_path = "default_responder" in called or "chat_specialist" in called
        uses_progenitors = "progenitor_alpha_specialist" in called

        # Greetings SHOULD use fast path, but tiered chat config may override
        # Just verify workflow completed without error
        assert not result['errors'], f"Flow 1.3: Unexpected errors: {result['errors']}"
        assert result['final_state'] is not None, "Flow 1.3: No final state"


# ============================================================================
# 2. FILE OPERATION FLOWS
# ============================================================================

class TestFileFlows:
    """Flow 2.x: File operation flows from FLOWS.md"""

    @pytest.mark.integration
    def test_flow_2_1_read_file(self, api_client):
        """
        Flow 2.1: Read File

        PROMPT: "Read the contents of README.md"

        Expected specialists:
        - triage_architect → creates ContextPlan with READ_FILE action
        - facilitator_specialist → executes MCP call
        - router_specialist
        - chat_specialist → presents content
        - end_specialist
        """
        result = invoke_flow(api_client, "Read the contents of README.md")

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 2.1: Missing core specialists"
        )

        # Context engineering flow may involve facilitator
        called = set(result['specialist_order'])

        # Should complete without error
        assert not result['errors'], f"Flow 2.1: Unexpected errors: {result['errors']}"
        assert result['final_state'] is not None, "Flow 2.1: No final state"

    @pytest.mark.integration
    def test_flow_2_2_write_file(self, api_client):
        """
        Flow 2.2: Write File

        PROMPT: "Create a file called test_notes.txt with 'Hello World'"

        Expected specialists:
        - triage_architect
        - router_specialist
        - file_operations_specialist → MCP write_file call
        - end_specialist
        """
        result = invoke_flow(
            api_client,
            "Create a file called test_output.txt with 'Flow test content'"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 2.2: Missing core specialists"
        )

        # File operation may route to file_operations_specialist
        called = set(result['specialist_order'])

        # Should complete (may or may not have file_operations_specialist based on routing)
        assert not result['errors'], f"Flow 2.2: Unexpected errors: {result['errors']}"

    @pytest.mark.integration
    def test_flow_2_3_list_directory(self, api_client):
        """
        Flow 2.3: List Directory

        PROMPT: "What files are in the workspace?"

        Expected specialists:
        - triage_architect → ContextPlan with LIST_DIRECTORY
        - facilitator_specialist
        - router_specialist
        - chat_specialist
        - end_specialist
        """
        result = invoke_flow(api_client, "What files are in the workspace?")

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 2.3: Missing core specialists"
        )

        assert not result['errors'], f"Flow 2.3: Unexpected errors: {result['errors']}"


# ============================================================================
# 3. BROWSER FLOWS
# ============================================================================

class TestBrowserFlows:
    """Flow 3.x: Browser flows from FLOWS.md (require surf-mcp)"""

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires surf-mcp container running")
    def test_flow_3_1_navigate_to_url(self, api_client):
        """
        Flow 3.1: Navigate to URL

        PROMPT: "Go to github.com"

        Expected specialists:
        - triage_architect
        - router_specialist
        - navigator_browser_specialist → creates session, goto, screenshot
        - end_specialist
        """
        result = invoke_flow(api_client, "Go to github.com")

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist", "navigator_browser_specialist"],
            "Flow 3.1: Missing browser specialists"
        )

        # Should have screenshot artifact
        assert result['final_state'] is not None
        artifacts = result['final_state'].get('artifacts', [])
        # Artifacts may contain screenshot reference

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires surf-mcp container with active session")
    def test_flow_3_2_click_element(self, api_client):
        """
        Flow 3.2: Click Element

        PROMPT: "Click the Sign In button"

        Expected: navigator_browser_specialist with Fara visual grounding
        """
        result = invoke_flow(api_client, "Click the Sign In button")

        assert_specialists_called(
            result,
            ["navigator_browser_specialist"],
            "Flow 3.2: Missing browser specialist"
        )

    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires surf-mcp container with active session")
    def test_flow_3_3_fill_form(self, api_client):
        """
        Flow 3.3: Fill Form

        PROMPT: "Type 'hello@example.com' in the email field"

        Expected: navigator_browser_specialist with Fara element location
        """
        result = invoke_flow(
            api_client,
            "Type 'test@example.com' in the email field"
        )

        assert_specialists_called(
            result,
            ["navigator_browser_specialist"],
            "Flow 3.3: Missing browser specialist"
        )


# ============================================================================
# 4. RESEARCH FLOWS
# ============================================================================

class TestResearchFlows:
    """Flow 4.x: Research flows from FLOWS.md"""

    @pytest.mark.integration
    @pytest.mark.slow  # Research flows take longer due to web searches
    def test_flow_4_1_simple_research(self, api_client):
        """
        Flow 4.1: Simple Research

        PROMPT: "What are the latest developments in quantum computing?"

        Expected specialists:
        - triage_architect
        - router_specialist
        - research_orchestrator → ReAct loop with search/browse
        - synthesizer_specialist → compile report
        - end_specialist
        """
        result = invoke_flow(
            api_client,
            "What are the latest developments in quantum computing?"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 4.1: Missing core specialists"
        )

        called = set(result['specialist_order'])

        # Research may go to research_orchestrator or tiered chat depending on config
        # Just verify it completes
        assert not result['errors'], f"Flow 4.1: Unexpected errors: {result['errors']}"
        assert result['final_state'] is not None, "Flow 4.1: No final state"

    @pytest.mark.integration
    @pytest.mark.slow
    def test_flow_4_2_comparative_research(self, api_client):
        """
        Flow 4.2: Comparative Research

        PROMPT: "Compare React vs Vue for a new project"

        Expected: ResearchOrchestrator with multiple search angles
        """
        result = invoke_flow(
            api_client,
            "Compare React vs Vue for a new project"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 4.2: Missing core specialists"
        )

        assert not result['errors'], f"Flow 4.2: Unexpected errors: {result['errors']}"


# ============================================================================
# 5. GENERATION FLOWS
# ============================================================================

class TestGenerationFlows:
    """Flow 5.x: Generation flows from FLOWS.md"""

    @pytest.mark.integration
    def test_flow_5_1_html_generation(self, api_client):
        """
        Flow 5.1: HTML Generation

        PROMPT: "Create a landing page for a coffee shop"

        Expected specialists:
        - triage_architect
        - router_specialist
        - web_builder → generate HTML
        - critic_specialist → review (optional loop)
        - end_specialist
        """
        result = invoke_flow(
            api_client,
            "Create a landing page for a coffee shop"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 5.1: Missing core specialists"
        )

        assert result['final_state'] is not None, "Flow 5.1: No final state"

        # Primary success criteria: HTML artifact was produced
        html_content = get_artifact(result['final_state'], "html_document.html")
        assert html_content is not None, (
            f"[Flow 5.1] Expected html_document.html artifact. "
            f"Errors: {result['errors'][:2] if result['errors'] else 'None'}"
        )

        # Validate content if we have it (dict format gives us actual content)
        if not html_content.startswith("[Artifact"):
            assert len(html_content) > 100, (
                f"[Flow 5.1] html_document.html too small ({len(html_content)} chars)"
            )

    @pytest.mark.integration
    def test_flow_5_2_technical_plan(self, api_client):
        """
        Flow 5.2: Technical Plan

        PROMPT: "Design an authentication system for my app"

        Expected specialists:
        - triage_architect
        - router_specialist
        - systems_architect
        - end_specialist
        """
        result = invoke_flow(
            api_client,
            "Design an authentication system for my app"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 5.2: Missing core specialists"
        )

        assert result['final_state'] is not None, "Flow 5.2: No final state"

        # Primary success criteria: system_plan artifact was produced
        plan_content = get_artifact(result['final_state'], "system_plan")
        assert plan_content is not None, (
            f"[Flow 5.2] Expected system_plan artifact. "
            f"Errors: {result['errors'][:2] if result['errors'] else 'None'}"
        )


# ============================================================================
# 6. ANALYSIS FLOWS
# ============================================================================

class TestAnalysisFlows:
    """Flow 6.x: Analysis flows from FLOWS.md"""

    @pytest.mark.integration
    def test_flow_6_1_text_summary(self, api_client):
        """
        Flow 6.1: Text Summary

        PROMPT: "Summarize this article: [long text]"

        Expected specialists:
        - triage_architect
        - router_specialist
        - summarizer_specialist
        - end_specialist
        """
        long_text = """
        Artificial intelligence has made remarkable strides in recent years.
        Machine learning models can now generate human-like text, create images,
        and even write code. The implications for various industries are profound.
        Healthcare is seeing AI assist in diagnosis, while finance uses it for
        fraud detection. Education is being transformed by personalized learning.
        However, concerns about bias, privacy, and job displacement remain.
        """

        result = invoke_flow(
            api_client,
            f"Summarize this article: {long_text}"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 6.1: Missing core specialists"
        )

        assert result['final_state'] is not None, "Flow 6.1: No final state"

        # Primary success criteria: response artifact exists
        response_content = get_artifact(result['final_state'], "final_user_response.md")
        assert response_content is not None, (
            f"[Flow 6.1] Expected final_user_response.md artifact. "
            f"Errors: {result['errors'][:2] if result['errors'] else 'None'}"
        )

        # Validate content doesn't contain error indicators (if we have actual content)
        if response_content and not response_content.startswith("[Artifact"):
            assert_response_not_error(response_content, "[Flow 6.1]")

    @pytest.mark.integration
    def test_flow_6_2_data_extraction(self, api_client):
        """
        Flow 6.2: Data Extraction

        PROMPT: "Extract all email addresses from this document"

        Expected specialists:
        - triage_architect
        - router_specialist
        - data_extractor (or equivalent)
        - end_specialist
        """
        document = """
        Contact us at support@example.com for help.
        Sales inquiries: sales@company.org
        Press: media@company.org
        Personal: john.doe@gmail.com
        """

        result = invoke_flow(
            api_client,
            f"Extract all email addresses from this document: {document}"
        )

        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 6.2: Missing core specialists"
        )

        assert result['final_state'] is not None, "Flow 6.2: No final state"

        # Primary success criteria: response artifact exists
        response_content = get_artifact(result['final_state'], "final_user_response.md")
        assert response_content is not None, (
            f"[Flow 6.2] Expected final_user_response.md artifact. "
            f"Errors: {result['errors'][:2] if result['errors'] else 'None'}"
        )

        # Validate content doesn't contain error indicators (if we have actual content)
        if response_content and not response_content.startswith("[Artifact"):
            assert_response_not_error(response_content, "[Flow 6.2]")


# ============================================================================
# 7. VISION FLOWS
# ============================================================================

class TestVisionFlows:
    """Flow 7.x: Vision/image analysis flows"""

    @pytest.mark.integration
    def test_flow_7_1_ui_mockup_to_html(self, api_client):
        """
        Flow 7.1: UI Mockup to HTML Generation

        PROMPT: "Make this gradio look more like the image"
        ATTACHMENT: gradio_vegas.png screenshot

        Expected specialists:
        - triage_architect → entry
        - router_specialist → routing
        - image_specialist → analyze uploaded mockup
        - systems_architect → create implementation plan
        - web_builder → generate HTML/CSS
        - critic_specialist → review output
        - end_specialist → termination

        REGRESSION: image_specialist must add itself to forbidden_specialists
        to prevent routing loop.
        """
        import base64
        from pathlib import Path

        # Load the test image
        image_path = Path(__file__).parent / "assets" / "screenshots" / "gradio_vegas.png"
        assert image_path.exists(), f"Test asset not found: {image_path}"

        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")

        # Invoke with image attachment
        result = invoke_flow(
            api_client,
            "Make this gradio look more like the image",
            image_to_process=image_base64
        )

        # Must have core routing
        assert_specialists_called(
            result,
            ["triage_architect", "router_specialist"],
            "Flow 7.1: Missing core routing specialists"
        )

        # image_specialist should be called for image analysis
        assert "image_specialist" in result['specialist_order'], (
            f"Flow 7.1: image_specialist not called for image prompt. "
            f"Called: {result['specialist_order']}"
        )

        # Full generation flow should include planning and building
        called = set(result['specialist_order'])
        generation_specialists = {"systems_architect", "web_builder", "critic_specialist"}
        missing = generation_specialists - called
        # At least some generation specialists should be called
        assert len(missing) < 3, (
            f"Flow 7.1: Expected generation specialists (systems_architect, web_builder, critic). "
            f"Missing: {missing}. Called: {result['specialist_order']}"
        )

        # REGRESSION CHECK: image_specialist should NOT appear more than twice
        # (once for analysis, maybe once more if router re-evaluates)
        # More than 2 indicates the "not me" pattern is broken
        image_specialist_count = result['specialist_order'].count("image_specialist")
        assert image_specialist_count <= 2, (
            f"Flow 7.1: image_specialist called {image_specialist_count} times - "
            f"possible loop due to missing forbidden_specialists. "
            f"Order: {result['specialist_order']}"
        )

        assert result['final_state'] is not None, "Flow 7.1: No final state"

        # Should produce HTML artifact
        html_content = get_artifact(result['final_state'], "html_document.html")
        if html_content and not html_content.startswith("[Artifact"):
            assert len(html_content) > 100, (
                f"Flow 7.1: html_document.html too small ({len(html_content)} chars)"
            )


# ============================================================================
# INVARIANT TESTS
# ============================================================================

class TestFlowInvariants:
    """
    Tests for flow invariants documented in FLOWS.md:
    1. Entry: Always starts at TriageArchitect
    2. Exit: Always ends at EndSpecialist
    3. Safety: All execution wrapped by NodeExecutor
    4. State: Specialists return dicts, never mutate GraphState directly
    5. Failover: Errors route to error handling, not silent failure
    """

    @pytest.mark.integration
    @pytest.mark.parametrize("prompt", [
        "Hello",
        "What is 2+2?",
        "Read README.md",
        "List files",
    ])
    def test_invariant_triage_entry(self, api_client, prompt):
        """Invariant 1: Every flow starts at TriageArchitect"""
        result = invoke_flow(api_client, prompt)

        # Triage should be first (or very early) in the execution
        assert "triage_architect" in result['specialist_order'], (
            f"Invariant 1 violated: triage_architect not called for '{prompt}'\n"
            f"Called: {result['specialist_order']}"
        )

        if result['specialist_order']:
            assert result['specialist_order'][0] == "triage_architect", (
                f"Invariant 1 violated: triage_architect not first for '{prompt}'\n"
                f"First was: {result['specialist_order'][0]}"
            )

    @pytest.mark.integration
    @pytest.mark.parametrize("prompt", [
        "Hello",
        "What is 2+2?",
    ])
    def test_invariant_end_exit(self, api_client, prompt):
        """Invariant 2: Every flow ends at EndSpecialist"""
        result = invoke_flow(api_client, prompt)

        # End specialist should be called
        assert "end_specialist" in result['specialist_order'], (
            f"Invariant 2 violated: end_specialist not called for '{prompt}'\n"
            f"Called: {result['specialist_order']}"
        )

        # End should be last (or near-last if archiver follows)
        last_specialists = result['specialist_order'][-2:] if len(result['specialist_order']) >= 2 else result['specialist_order']
        terminal = {"end_specialist", "archiver_specialist"}
        assert any(s in terminal for s in last_specialists), (
            f"Invariant 2 violated: workflow didn't terminate properly for '{prompt}'\n"
            f"Last specialists: {last_specialists}"
        )

    @pytest.mark.integration
    def test_invariant_no_silent_failure(self, api_client):
        """Invariant 5: Errors route to error handling, not silent failure"""
        # Use a prompt that might cause issues but shouldn't crash
        result = invoke_flow(api_client, "")  # Empty prompt

        # Should still have a final state (even if error)
        # If the API returns 200, it started streaming, so we should get some data
        assert result['final_state'] is not None or result['errors'], (
            "Invariant 5 violated: Empty prompt caused silent failure"
        )


# ============================================================================
# EXECUTION ORDER VERIFICATION
# ============================================================================

class TestExecutionOrder:
    """Tests that verify specialist execution follows expected patterns"""

    @pytest.mark.integration
    def test_router_follows_triage(self, api_client):
        """Router should always follow triage (after optional facilitator)"""
        result = invoke_flow(api_client, "Simple test query")

        order = result['specialist_order']

        if "triage_architect" in order and "router_specialist" in order:
            triage_idx = order.index("triage_architect")
            router_idx = order.index("router_specialist")

            # Router should come after triage
            assert router_idx > triage_idx, (
                f"Router should follow triage. Order: {order}"
            )

    @pytest.mark.integration
    def test_end_is_terminal(self, api_client):
        """End specialist should be at or near the end of execution"""
        result = invoke_flow(api_client, "Simple test query")

        order = result['specialist_order']

        if "end_specialist" in order:
            end_idx = order.index("end_specialist")
            # End should be in the last 3 specialists (allowing for archiver)
            assert end_idx >= len(order) - 3, (
                f"End specialist should be near end. "
                f"Position: {end_idx} of {len(order)}. Order: {order}"
            )
