# app/tests/integration/test_fara_smoke.py
"""
Minimal smoke test for Fara-7B vision model.

This test creates a simple synthetic image and asks Fara to locate
an element - confirming the RTX 8000 connection works and the model
responds at all.

Run with:
    pytest app/tests/integration/test_fara_smoke.py -v -s

The -s flag shows print output so you can see the raw model response.
"""

import pytest
import base64
import io
from PIL import Image, ImageDraw, ImageFont

pytestmark = [
    pytest.mark.integration,
    pytest.mark.fara,
    pytest.mark.live_llm,
]


def create_synthetic_test_image() -> str:
    """
    Create a simple test image: white background with an orange button.

    Returns base64-encoded PNG.
    """
    # Create 800x600 white image
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)

    # Draw an orange "button" rectangle in the center-right area
    button_x1, button_y1 = 500, 250
    button_x2, button_y2 = 700, 300
    draw.rectangle([button_x1, button_y1, button_x2, button_y2], fill="orange", outline="darkorange", width=2)

    # Add text inside the button (using default font)
    try:
        # Try to add text - will use default bitmap font
        text = "EXECUTE"
        # Center the text roughly in the button
        text_x = button_x1 + 50
        text_y = button_y1 + 15
        draw.text((text_x, text_y), text, fill="white")
    except Exception:
        pass  # Skip text if font issues

    # Draw a smaller blue rectangle in top-left (status indicator)
    draw.rectangle([50, 50, 200, 100], fill="lightblue", outline="blue", width=2)
    draw.text((70, 65), "READY", fill="darkblue")

    # Encode to base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def fara_adapter():
    """
    Create LMStudioAdapter for Fara-7B.

    This is a minimal fixture that just creates the adapter,
    without the full FaraService wrapper.
    """
    from app.src.utils.config_loader import ConfigLoader
    from app.src.llm.lmstudio_adapter import LMStudioAdapter

    # Load config
    try:
        config = ConfigLoader().get_config()
    except Exception as e:
        pytest.skip(f"Could not load config: {e}")

    # Get fara_vision provider
    llm_providers = config.get("llm_providers", {})
    fara_config = llm_providers.get("fara_vision")
    if not fara_config:
        pytest.skip("No 'fara_vision' provider in user_settings.yaml")

    base_url = fara_config.get("base_url")
    if not base_url:
        pytest.skip("fara_vision missing base_url - check LMSTUDIO_SERVERS env var")

    system_prompt = (
        "You are a vision model for UI testing. "
        "When asked to locate an element, respond with JSON: "
        '{"found": true/false, "x": number, "y": number, "confidence": 0.0-1.0}'
    )

    try:
        adapter = LMStudioAdapter.from_config(
            provider_config=fara_config,
            system_prompt=system_prompt
        )
        return adapter
    except Exception as e:
        pytest.skip(f"Could not create adapter: {e}")


class TestFaraSmoke:
    """Minimal smoke tests - just verify Fara responds to images."""

    def test_fara_responds_to_synthetic_image(self, fara_adapter):
        """
        SMOKE TEST: Send a synthetic image to Fara and print the response.

        This test passes if we get ANY response from the model.
        The response quality doesn't matter - we just want to confirm
        the connection works.
        """
        from app.src.llm.adapter import StandardizedLLMRequest
        from langchain_core.messages import HumanMessage

        # Create test image
        test_image = create_synthetic_test_image()
        print(f"\n[TEST] Created synthetic test image ({len(test_image)} chars base64)")

        # Build request
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Locate the orange EXECUTE button in this image.")],
            image_data=test_image
        )

        print("[TEST] Sending to Fara-7B on RTX 8000...")

        # Call the model
        response = fara_adapter.invoke(request)

        print(f"[TEST] Raw response: {response}")

        # Just verify we got something back
        assert response is not None, "Got no response from Fara"
        assert isinstance(response, dict), f"Expected dict, got {type(response)}"

        # Check if we got text or JSON
        if "text_response" in response:
            print(f"[TEST] Text response: {response['text_response']}")
        if "json_response" in response:
            print(f"[TEST] JSON response: {response['json_response']}")

        print("[TEST] SUCCESS - Fara responded!")

    def test_fara_verify_element_exists(self, fara_adapter):
        """
        SMOKE TEST: Ask Fara if an element exists in the image.
        """
        from app.src.llm.adapter import StandardizedLLMRequest
        from langchain_core.messages import HumanMessage

        test_image = create_synthetic_test_image()

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Does this image contain a blue READY indicator? Answer with JSON: {\"found\": true/false}")],
            image_data=test_image
        )

        print("\n[TEST] Asking Fara if blue READY indicator exists...")

        response = fara_adapter.invoke(request)

        print(f"[TEST] Response: {response}")

        assert response is not None
        print("[TEST] SUCCESS - Fara responded to verify question!")
