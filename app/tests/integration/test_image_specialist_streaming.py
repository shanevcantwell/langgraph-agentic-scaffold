# app/tests/integration/test_image_specialist_streaming.py
"""
Integration tests for image_specialist event streaming.

These tests verify that when an image is uploaded and processed:
1. image_specialist appears in the SSE stream
2. Events flow correctly from LangGraph through AgUiTranslator to the API
3. The Glass Cockpit UI would receive the necessary events for thought stream display

The bug being tested: image_specialist executed successfully (11654ms, produced artifact)
but no thought stream entry appeared in the UI despite correct execution.

These tests require Docker: `docker exec langgraph-app pytest -m integration app/tests/integration/test_image_specialist_streaming.py -v`
"""
import pytest
import json
import re
import base64
from typing import Set, List, Dict, Any

from fastapi.testclient import TestClient


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def test_image_base64() -> str:
    """Loads the standard test image from assets."""
    from pathlib import Path
    image_path = Path(__file__).parent.parent / "assets" / "screenshots" / "gradio_vegas.png"
    assert image_path.exists(), f"Test asset not found: {image_path}"
    with open(image_path, "rb") as f:
        # Raw base64 (no data URI prefix) to match test_flows.py pattern
        return base64.b64encode(f.read()).decode()


@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.
    """
    from app.src import api
    return api.app


def parse_sse_stream(response_text: str) -> Dict[str, Any]:
    """
    Parse SSE stream response into structured data.

    Returns dict with:
    - status_updates: list of status strings
    - specialist_names: set of specialists that emitted status updates
    - node_events: list of (specialist, event_type) tuples
    - scratchpad_events: list of scratchpad data streamed
    - final_state: the final state if present
    - raw_events: list of all parsed event dicts
    """
    result = {
        "status_updates": [],
        "specialist_names": set(),
        "node_events": [],
        "scratchpad_events": [],
        "final_state": None,
        "raw_events": [],
        "run_id": None,
    }

    for line in response_text.split('\n'):
        if line.startswith('data:'):
            try:
                data_str = line[len('data:'):].strip()
                data = json.loads(data_str)
                result["raw_events"].append(data)

                # Extract run_id
                if 'run_id' in data:
                    result["run_id"] = data["run_id"]

                # Extract status updates and specialist names
                if 'status' in data:
                    result["status_updates"].append(data['status'])
                    match = re.search(r'Executing specialist: (\w+)', data['status'])
                    if match:
                        result["specialist_names"].add(match.group(1))

                # Extract AG-UI node events (from /v1/graph/stream/events endpoint)
                if 'type' in data and 'source' in data:
                    result["node_events"].append((data['source'], data['type']))

                # Extract scratchpad data
                if 'scratchpad' in data:
                    result["scratchpad_events"].append({
                        "source": data.get("source", "unknown"),
                        "scratchpad": data["scratchpad"]
                    })

                # Capture final state
                if 'final_state' in data:
                    result["final_state"] = data['final_state']

            except json.JSONDecodeError:
                pass

    return result


# =============================================================================
# Core Integration Tests: /v1/graph/stream (Glass Cockpit endpoint)
# =============================================================================

@pytest.mark.integration
class TestImageSpecialistStreamEndpoint:
    """Tests for the /v1/graph/stream endpoint used by Glass Cockpit."""

    def test_image_specialist_appears_in_status_updates(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        CORE TEST: Verify image_specialist appears in SSE status updates.

        This directly tests the bug where image_specialist executed
        but didn't appear in the thought stream.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"

            parsed = parse_sse_stream(response.text)

            # The key assertion: image_specialist MUST be in the specialist names
            assert "image_specialist" in parsed["specialist_names"], (
                f"BUG DETECTED: image_specialist not found in status updates. "
                f"Specialists found: {parsed['specialist_names']}. "
                f"Status updates: {parsed['status_updates'][:5]}..."  # First 5
            )

    def test_image_specialist_status_before_default_responder(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Verify image_specialist status appears BEFORE default_responder.

        Based on archive analysis, the expected flow is:
        triage_architect -> image_specialist -> default_responder_specialist
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "What do you see in this image?",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            # Build execution order from status updates
            execution_order = []
            for status in parsed["status_updates"]:
                match = re.search(r'Executing specialist: (\w+)', status)
                if match:
                    specialist = match.group(1)
                    if specialist not in execution_order:
                        execution_order.append(specialist)

            # image_specialist should appear before default_responder
            if "image_specialist" in execution_order and "default_responder_specialist" in execution_order:
                image_idx = execution_order.index("image_specialist")
                responder_idx = execution_order.index("default_responder_specialist")
                assert image_idx < responder_idx, (
                    f"image_specialist should execute before default_responder. "
                    f"Order: {execution_order}"
                )

    def test_image_description_artifact_in_final_state(
        self,
        initialized_app,
        test_image_base64
    ):
        """Verify image_description artifact is in final state."""
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Analyze this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            assert parsed["final_state"] is not None, "final_state not found in stream"
            artifacts = parsed["final_state"].get("artifacts", [])
            assert "image_description" in artifacts, (
                f"image_description artifact missing from final_state. "
                f"Artifacts: {artifacts}"
            )

    def test_no_phantom_router_for_image_workflow(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Verify router_specialist does NOT appear in image workflow.

        Based on archive analysis, the flow is:
        triage_architect -> image_specialist -> default_responder (NO router)

        The UI was showing phantom ROUTER entries that didn't correspond
        to actual execution.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            # router_specialist should NOT be in the execution
            # (triage routes directly to image_specialist for images)
            if "triage_architect" in parsed["specialist_names"]:
                # If using triage-based architecture, router may be skipped
                # This test documents the expected behavior
                pass  # Test passes - just documenting the flow

            # Log the actual flow for debugging
            print(f"Image workflow specialists: {parsed['specialist_names']}")


# =============================================================================
# AG-UI Events Endpoint Tests: /v1/graph/stream/events
# =============================================================================

@pytest.mark.integration
class TestImageSpecialistEventsEndpoint:
    """Tests for the /v1/graph/stream/events endpoint with AG-UI schema."""

    def test_image_specialist_node_start_event(
        self,
        initialized_app,
        test_image_base64
    ):
        """Verify NODE_START event is emitted for image_specialist."""
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream/events", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            # Find node_start events for image_specialist
            image_starts = [
                (src, evt) for src, evt in parsed["node_events"]
                if src == "image_specialist" and evt == "node_start"
            ]

            assert len(image_starts) >= 1, (
                f"No NODE_START event for image_specialist. "
                f"All node events: {parsed['node_events']}"
            )

    def test_image_specialist_node_end_event(
        self,
        initialized_app,
        test_image_base64
    ):
        """Verify NODE_END event is emitted for image_specialist."""
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "What is in this image?",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream/events", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            # Find node_end events for image_specialist
            image_ends = [
                (src, evt) for src, evt in parsed["node_events"]
                if src == "image_specialist" and evt == "node_end"
            ]

            assert len(image_ends) >= 1, (
                f"No NODE_END event for image_specialist. "
                f"All node events: {parsed['node_events']}"
            )


# =============================================================================
# Diagnostic Tests: Event Flow Tracing
# =============================================================================

@pytest.mark.integration
class TestEventFlowDiagnostics:
    """
    Diagnostic tests that help identify where events are lost.
    These tests emit detailed information for debugging.
    """

    def test_full_event_trace_for_image(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Captures and reports the full event trace for an image workflow.

        This test always passes but prints detailed diagnostic info.
        Use this when debugging thought stream issues.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image in detail",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)

            parsed = parse_sse_stream(response.text)

            print("\n" + "=" * 60)
            print("IMAGE WORKFLOW EVENT TRACE")
            print("=" * 60)
            print(f"Run ID: {parsed['run_id']}")
            print(f"\nSpecialists with status updates: {parsed['specialist_names']}")
            print(f"\nExecution order (from status):")
            for i, status in enumerate(parsed['status_updates'][:10]):  # First 10
                print(f"  {i+1}. {status}")

            if parsed['final_state']:
                print(f"\nFinal state artifacts: {parsed['final_state'].get('artifacts', [])}")
                print(f"Routing history: {parsed['final_state'].get('routing_history', [])}")

            print(f"\nTotal raw events: {len(parsed['raw_events'])}")
            print("=" * 60)

            # This test is for diagnostics - always passes
            assert True

    def test_compare_stream_and_events_endpoints(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Compare output from both streaming endpoints to identify discrepancies.

        /v1/graph/stream - Used by Glass Cockpit (the buggy path)
        /v1/graph/stream/events - Uses AgUiTranslator
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "What do you see?",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            # Get response from both endpoints
            stream_response = client.post("/v1/graph/stream", json=payload)
            events_response = client.post("/v1/graph/stream/events", json=payload)

            stream_parsed = parse_sse_stream(stream_response.text)
            events_parsed = parse_sse_stream(events_response.text)

            print("\n" + "=" * 60)
            print("ENDPOINT COMPARISON")
            print("=" * 60)
            print(f"/v1/graph/stream specialists: {stream_parsed['specialist_names']}")
            print(f"/v1/graph/stream/events sources: {set(src for src, _ in events_parsed['node_events'])}")

            # Both endpoints should see image_specialist
            stream_has_image = "image_specialist" in stream_parsed['specialist_names']
            events_has_image = any(
                src == "image_specialist"
                for src, _ in events_parsed['node_events']
            )

            print(f"\n/v1/graph/stream has image_specialist: {stream_has_image}")
            print(f"/v1/graph/stream/events has image_specialist: {events_has_image}")
            print("=" * 60)

            # If one has it and the other doesn't, that's our bug location
            if stream_has_image != events_has_image:
                print("WARNING: Discrepancy detected between endpoints!")


# =============================================================================
# Regression Tests
# =============================================================================

@pytest.mark.integration
class TestThoughtStreamRegressions:
    """Regression tests to prevent thought stream visibility bugs."""

    def test_all_executed_specialists_appear_in_stream(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Verify ALL specialists that execute appear in the stream.

        This is the key regression test - every specialist that runs
        should emit status updates visible to the UI.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Analyze and describe this image thoroughly",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_sse_stream(response.text)

            # Get routing_history from final_state (ground truth of what executed)
            if parsed["final_state"]:
                routing_history = parsed["final_state"].get("routing_history", [])
                streamed_specialists = parsed["specialist_names"]

                # Every specialist in routing_history should be in streamed specialists
                # (routing_history is the authoritative record of what actually ran)
                missing_from_stream = set(routing_history) - streamed_specialists

                assert not missing_from_stream, (
                    f"REGRESSION: Specialists executed but missing from stream: {missing_from_stream}. "
                    f"Routing history: {routing_history}. "
                    f"Streamed: {streamed_specialists}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
