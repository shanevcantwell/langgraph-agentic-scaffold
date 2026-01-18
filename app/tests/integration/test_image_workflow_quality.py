# app/tests/integration/test_image_workflow_quality.py
"""
Integration tests for image workflow QUALITY - "what good looks like".

These tests verify the end-to-end behavior of image analysis workflows:
1. image_specialist should produce a description artifact
2. The final user response should USE that description (not ask for the image again)
3. The routing after image_specialist should lead to artifact utilization

Bug context: image_specialist successfully produced a 3839-byte description,
but the final response was "please share the image" - the artifact wasn't used.

Run: docker exec langgraph-app pytest app/tests/integration/test_image_workflow_quality.py -v
"""
import pytest
import json
import base64
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def test_image_base64() -> str:
    """Loads the standard test image from assets."""
    from pathlib import Path
    image_path = Path(__file__).parent.parent / "assets" / "screenshots" / "gradio_vegas.png"
    assert image_path.exists(), f"Test asset not found: {image_path}"
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode()


@pytest.fixture(scope="module")
def initialized_app():
    """Provides an initialized FastAPI app."""
    from app.src import api
    return api.app


def parse_stream_response(response_text: str) -> dict:
    """Parse SSE stream and extract key information."""
    result = {
        "specialists": [],
        "final_state": None,
        "final_response": None,
        "artifacts": {},
        "errors": []
    }

    for line in response_text.split('\n'):
        if line.startswith('data:'):
            try:
                data = json.loads(line[len('data:'):].strip())

                # Track specialist execution
                if 'status' in data and 'Executing specialist:' in data['status']:
                    import re
                    match = re.search(r'Executing specialist: (\w+)', data['status'])
                    if match and match.group(1) not in result["specialists"]:
                        result["specialists"].append(match.group(1))

                # Track artifacts
                if 'artifacts' in data and isinstance(data['artifacts'], dict):
                    result["artifacts"].update(data['artifacts'])

                # Capture final state
                if 'final_state' in data:
                    result["final_state"] = data['final_state']

                # Capture errors
                if 'error' in data:
                    result["errors"].append(data['error'])

            except json.JSONDecodeError:
                pass

    # Extract final response from final_state
    if result["final_state"]:
        # Check artifacts for final_user_response.md
        artifacts = result["final_state"].get("artifacts", [])
        if isinstance(artifacts, dict):
            result["final_response"] = artifacts.get("final_user_response.md")

        # Also check messages
        messages = result["final_state"].get("messages_summary", [])
        if not result["final_response"] and messages:
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("type") == "ai":
                    result["final_response"] = msg.get("content", "")
                    break

    return result


# =============================================================================
# TESTS FOR "WHAT GOOD LOOKS LIKE"
# =============================================================================

@pytest.mark.integration
class TestImageWorkflowQuality:
    """Tests that image workflows produce USEFUL responses, not clarification requests."""

    def test_image_description_artifact_is_produced(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        BASELINE: Verify image_specialist produces the image_description artifact.

        This confirms the image analysis pipeline works. If this fails,
        the problem is in image_specialist itself.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_stream_response(response.text)

            # image_specialist should have run
            assert "image_specialist" in parsed["specialists"], (
                f"image_specialist should execute. Got: {parsed['specialists']}"
            )

            # image_description artifact should exist
            assert parsed["final_state"] is not None, "No final_state in response"
            artifacts = parsed["final_state"].get("artifacts", [])

            # artifacts might be a list of names or a dict
            if isinstance(artifacts, list):
                assert "image_description" in artifacts, (
                    f"image_description artifact missing. Artifacts: {artifacts}"
                )
            elif isinstance(artifacts, dict):
                assert "image_description" in artifacts, (
                    f"image_description artifact missing. Artifacts: {list(artifacts.keys())}"
                )

    def test_final_response_uses_image_description(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        CRITICAL: Final response should USE the image_description, not ask for the image.

        This is the key quality test. After image_specialist produces a description,
        the final user response should incorporate that description.

        ANTI-PATTERN (bug): "Could you please share the image?"
        GOOD PATTERN: "The image shows..." / "Based on my analysis..." / actual description
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "What do you see in this image?",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_stream_response(response.text)

            # Get the final response
            final_response = parsed.get("final_response", "")

            # Also check scratchpad user_response_snippets
            if not final_response and parsed["final_state"]:
                scratchpad = parsed["final_state"].get("scratchpad", {})
                if isinstance(scratchpad, dict):
                    snippets = scratchpad.get("user_response_snippets", [])
                    if snippets:
                        final_response = snippets[0] if isinstance(snippets, list) else str(snippets)

            assert final_response, "No final response found in output"

            # THE KEY ASSERTION: Response should NOT ask for the image
            bad_patterns = [
                "please share the image",
                "could you share the image",
                "could you please share",
                "share the image or describe",
                "provide the image",
                "upload the image",
                "I don't see an image",
                "no image was provided",
                "what image",
            ]

            response_lower = final_response.lower()
            for pattern in bad_patterns:
                assert pattern not in response_lower, (
                    f"BUG: Final response asks for image instead of using description.\n"
                    f"Bad pattern found: '{pattern}'\n"
                    f"Full response: {final_response[:500]}..."
                )

    def test_final_response_contains_description_content(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        QUALITY: Final response should contain substantive content from the description.

        Not just "here's the description" but actual descriptive content.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image in detail",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_stream_response(response.text)

            final_response = parsed.get("final_response", "")
            if not final_response and parsed["final_state"]:
                scratchpad = parsed["final_state"].get("scratchpad", {})
                if isinstance(scratchpad, dict):
                    snippets = scratchpad.get("user_response_snippets", [])
                    if snippets:
                        final_response = snippets[0] if isinstance(snippets, list) else str(snippets)

            # Response should have substantive length (not a one-liner asking for clarification)
            assert len(final_response) > 100, (
                f"Final response too short ({len(final_response)} chars). "
                f"Expected substantive description. Got: {final_response}"
            )


@pytest.mark.integration
class TestImageRoutingAfterAnalysis:
    """Tests for routing decisions after image_specialist completes."""

    def test_routing_does_not_go_to_default_responder_after_image(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        After image_specialist produces description, should NOT route to default_responder.

        default_responder is for greetings and fallback - it doesn't synthesize artifacts.
        The flow should go to a specialist that can use the image_description artifact.
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "Describe this image",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_stream_response(response.text)
            specialists = parsed["specialists"]

            # If image_specialist ran successfully...
            if "image_specialist" in specialists:
                # Check what ran AFTER image_specialist
                image_idx = specialists.index("image_specialist")
                after_image = specialists[image_idx + 1:] if image_idx < len(specialists) - 1 else []

                # default_responder should NOT be the next specialist after image_specialist
                # (It's okay if it appears earlier for a different reason)
                if "default_responder_specialist" in after_image:
                    # Check if it's immediately after image_specialist
                    if after_image and after_image[0] == "default_responder_specialist":
                        # This is the bug pattern!
                        pytest.fail(
                            f"BUG: default_responder_specialist immediately followed image_specialist.\n"
                            f"Full routing: {specialists}\n"
                            f"Expected: image_specialist → (router →) chat/tiered/end, not default_responder"
                        )

    def test_task_completes_after_image_analysis(
        self,
        initialized_app,
        test_image_base64
    ):
        """
        Image analysis workflow should complete (not loop indefinitely).
        """
        with TestClient(initialized_app) as client:
            payload = {
                "input_prompt": "What's in this image?",
                "text_to_process": None,
                "image_to_process": test_image_base64
            }

            response = client.post("/v1/graph/stream", json=payload)
            assert response.status_code == 200

            parsed = parse_stream_response(response.text)

            # Should have final_state indicating completion
            assert parsed["final_state"] is not None, "No final_state - workflow may not have completed"

            # Check task_is_complete
            task_complete = parsed["final_state"].get("task_is_complete", False)
            assert task_complete, (
                f"task_is_complete should be True after image analysis. "
                f"Final state: {json.dumps(parsed['final_state'], indent=2)[:500]}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
