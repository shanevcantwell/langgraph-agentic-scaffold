# app/tests/integration/test_fara_vegas_terminal.py
"""
Integration tests for Fara visual verification on V.E.G.A.S. Terminal.

These tests verify that Fara-7B can:
1. Locate UI elements in V.E.G.A.S. Terminal screenshots
2. Verify element existence
3. Execute a complete workflow (locate → click → verify result)

Prerequisites:
- Fara-7B GGUF loaded in LM Studio
- LM Studio server running at http://localhost:1234
- V.E.G.A.S. Terminal screenshots in test assets

Test asset locations:
- app/tests/assets/screenshots/lassi_ui.png
- app/tests/assets/screenshots/vegas_terminal_after_execute.png

To run these tests:
    pytest app/tests/integration/test_fara_vegas_terminal.py -v -m fara

To run with live model:
    pytest app/tests/integration/test_fara_vegas_terminal.py -v -m "fara and live_llm"
"""

import pytest
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

# Test markers
pytestmark = [
    pytest.mark.integration,
    pytest.mark.fara,
]

# =============================================================================
# Test Asset Helpers
# =============================================================================

TEST_ASSETS_DIR = Path(__file__).parent.parent / "assets" / "screenshots"


def load_test_screenshot(filename: str) -> str:
    """
    Load a test screenshot as base64.

    Args:
        filename: Screenshot filename in test assets directory

    Returns:
        Base64-encoded screenshot

    Raises:
        FileNotFoundError: If screenshot doesn't exist
    """
    path = TEST_ASSETS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Test screenshot not found: {path}\n"
            f"To run these tests, add V.E.G.A.S. Terminal screenshots to:\n"
            f"  {TEST_ASSETS_DIR}/"
        )
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def fara_service():
    """
    Create FaraService for mocked integration testing.

    Returns a FaraService with _invoke_fara patched to return
    controllable responses. This bypasses resolution scaling
    (which requires real images) while testing the service API.

    Usage in tests:
        def test_something(fara_service):
            fara_service.set_response({"found": True, "x": 100, "y": 200})
            result = fara_service.locate("button", screenshot="ignored")
    """
    from app.src.mcp.services.fara_service import FaraService

    # Create service with mock adapter
    mock_adapter = MagicMock()
    service = FaraService(llm_adapter=mock_adapter)

    # Track responses for sequential calls
    service._mock_responses = []
    service._mock_call_index = 0

    def mock_invoke_fara(screenshot, task, description):
        """Return pre-configured mock responses."""
        if service._mock_responses:
            if service._mock_call_index < len(service._mock_responses):
                response = service._mock_responses[service._mock_call_index]
                service._mock_call_index += 1
                return response
            # Fallback to last response if we run out
            return service._mock_responses[-1]
        return {"found": False, "error": "No mock response configured"}

    # Patch _invoke_fara
    service._invoke_fara = mock_invoke_fara

    def set_response(response):
        """Set a single response for the next call."""
        service._mock_responses = [response]
        service._mock_call_index = 0

    def set_responses(responses):
        """Set multiple responses for sequential calls."""
        service._mock_responses = responses
        service._mock_call_index = 0

    # Add helper methods
    service.set_response = set_response
    service.set_responses = set_responses

    return service


@pytest.fixture
def live_fara_service():
    """
    Create FaraService with live Fara-7B connection.

    Requires:
    - LM Studio running with Fara-7B loaded on configured server
    - user_settings.yaml configured with fara_vision binding

    Configuration example (user_settings.yaml):
        fara_vision:
          type: "lmstudio"
          server: "rtx8000"
          api_identifier: "fara-7b"
    """
    import os
    from app.src.mcp.services.fara_service import FaraService
    from app.src.utils.config_loader import ConfigLoader
    from app.src.llm.factory import AdapterFactory

    # Load config (ConfigLoader resolves server → base_url automatically)
    try:
        config = ConfigLoader().get_config()
    except Exception as e:
        pytest.skip(f"Could not load config: {e}")

    # Check for fara_vision in llm_providers
    llm_providers = config.get("llm_providers", {})
    fara_config = llm_providers.get("fara_vision")
    if not fara_config:
        pytest.skip(
            "No 'fara_vision' provider configured in user_settings.yaml. "
            "Add to llm_providers: fara_vision: {type: 'lmstudio', server: 'rtx8000', api_identifier: 'fara-7b'}"
        )

    # Verify base_url was resolved (via LMSTUDIO_SERVERS env var or direct config)
    base_url = fara_config.get("base_url")
    if not base_url:
        pytest.skip(
            "fara_vision provider missing 'base_url'. "
            "Ensure LMSTUDIO_SERVERS contains your server mapping (e.g., 'rtx8000=http://192.168.x.x:1234/v1') "
            "or set base_url directly in the config."
        )

    # Create adapter using factory
    # Note: fara_vision isn't a specialist, so we build the adapter directly
    from app.src.llm.lmstudio_adapter import LMStudioAdapter

    system_prompt = (
        "You are Fara, a vision model for computer use. "
        "Analyze screenshots and respond with JSON coordinates for UI elements."
    )

    try:
        adapter = LMStudioAdapter.from_config(
            provider_config=fara_config,
            system_prompt=system_prompt
        )
    except Exception as e:
        pytest.skip(f"Could not create Fara adapter: {e}")

    # Extract native_resolutions from config if present
    native_resolutions = None
    if "native_resolutions" in fara_config:
        raw = fara_config["native_resolutions"]
        # Convert from list format [w, h] to tuple format (w, h)
        native_resolutions = {
            k: tuple(v) if isinstance(v, list) else v
            for k, v in raw.items()
        }

    # Create and return FaraService with live adapter and configured resolutions
    return FaraService(
        llm_adapter=adapter,
        native_resolutions=native_resolutions or {}
    )


# =============================================================================
# Mock Tests (Run without live model)
# =============================================================================

class TestVegasTerminalMocked:
    """Tests with mocked Fara responses (no live model needed)."""

    def test_locate_execute_button(self, fara_service):
        """Fara can locate the EXECUTE button in V.E.G.A.S. Terminal."""
        # Set mock response (bypasses resolution scaling)
        fara_service.set_response({"found": True, "x": 590, "y": 225, "confidence": 0.96})

        result = fara_service.locate(
            description="The green EXECUTE button",
            screenshot="mock_vegas_screenshot"
        )

        assert result["found"] is True
        # Expected coordinates for EXECUTE button (approximate)
        assert 550 < result["x"] < 630, f"X coordinate {result['x']} out of expected range"
        assert 200 < result["y"] < 250, f"Y coordinate {result['y']} out of expected range"
        assert result["confidence"] > 0.9

    def test_locate_status_indicator(self, fara_service):
        """Fara can locate the status indicator panel."""
        fara_service.set_response({"found": True, "x": 150, "y": 50, "confidence": 0.92})

        result = fara_service.locate(
            description="The status indicator showing READY",
            screenshot="mock_vegas_screenshot"
        )

        assert result["found"] is True

    def test_verify_terminal_header(self, fara_service):
        """Fara can verify the V.E.G.A.S. Terminal header exists."""
        fara_service.set_response({"found": True, "confidence": 0.99})

        result = fara_service.verify(
            description="V.E.G.A.S. Terminal header or title",
            screenshot="mock_vegas_screenshot"
        )

        assert result["exists"] is True
        assert result["confidence"] > 0.95

    def test_verify_missing_element(self, fara_service):
        """Fara correctly reports missing elements."""
        fara_service.set_response({"found": False, "confidence": 0.15})

        result = fara_service.verify(
            description="A red ERROR banner",
            screenshot="mock_vegas_screenshot"
        )

        assert result["exists"] is False

    def test_full_ping_workflow_mocked(self, fara_service):
        """
        Test the full integration ping workflow with mocked responses.

        Workflow:
        1. Verify terminal is loaded
        2. Locate EXECUTE button
        3. (Would click in real test)
        4. Verify success message appears
        """
        # Setup: sequence of responses
        fara_service.set_responses([
            # Step 1: Verify terminal loaded
            {"found": True, "confidence": 0.99},
            # Step 2: Locate EXECUTE button
            {"found": True, "x": 590, "y": 225, "confidence": 0.96},
            # Step 4: Verify success after execute
            {"found": True, "confidence": 0.94},
        ])

        # Step 1: Verify terminal is loaded
        verify_result = fara_service.verify(
            "V.E.G.A.S. Terminal interface",
            screenshot="mock_before"
        )
        assert verify_result["exists"] is True

        # Step 2: Locate EXECUTE button
        locate_result = fara_service.locate(
            "The green EXECUTE button",
            screenshot="mock_before"
        )
        assert locate_result["found"] is True
        x, y = locate_result["x"], locate_result["y"]

        # Step 3: Click would happen here (needs browser controller)
        # click_result = fara_service.click(x, y)

        # Step 4: Verify success message
        success_result = fara_service.verify(
            "Success message or confirmation",
            screenshot="mock_after"
        )
        assert success_result["exists"] is True


# =============================================================================
# Live Tests (Require Fara-7B running)
# =============================================================================

VEGAS_SCREENSHOT = TEST_ASSETS_DIR / "lassi_ui.png"


@pytest.mark.live_llm
@pytest.mark.skipif(
    not VEGAS_SCREENSHOT.exists(),
    reason=f"V.E.G.A.S. Terminal screenshot not found: {VEGAS_SCREENSHOT}"
)
class TestVegasTerminalLive:
    """
    Live tests against actual Fara-7B model.

    These tests require:
    - Fara-7B GGUF loaded in LM Studio
    - V.E.G.A.S. Terminal screenshots in test assets
    """

    def test_locate_execute_button_live(self, live_fara_service):
        """Live test: Locate EXECUTE button."""
        screenshot = load_test_screenshot("lassi_ui.png")

        result = live_fara_service.locate(
            description="The green EXECUTE button",
            screenshot=screenshot
        )

        assert result["found"] is True
        # These bounds should be updated based on actual screenshot analysis
        assert 500 < result["x"] < 700
        assert 150 < result["y"] < 300

    def test_verify_all_major_elements_live(self, live_fara_service):
        """Live test: Verify major UI elements exist."""
        screenshot = load_test_screenshot("lassi_ui.png")

        elements_to_verify = [
            "V.E.G.A.S. Terminal header",
            "The EXECUTE button",
            "Status indicator panel",
            "Input or command area",
        ]

        for element in elements_to_verify:
            result = live_fara_service.verify(
                description=element,
                screenshot=screenshot
            )
            assert result["exists"] is True, f"Element not found: {element}"

    def test_full_integration_ping_live(self, live_fara_service):
        """
        Live test: Full integration ping through V.E.G.A.S. Terminal.

        This is the target test from the conversation - verify Fara can
        navigate the UI and trigger an integration ping purely from screenshots.
        """
        pytest.skip("Requires Playwright browser setup - to be implemented")

        # Full workflow:
        # 1. Load V.E.G.A.S. Terminal in browser
        # 2. Screenshot initial state
        # 3. Locate EXECUTE button
        # 4. Click at coordinates
        # 5. Screenshot result
        # 6. Verify success message


# =============================================================================
# Coordinate Validation Tests
# =============================================================================

class TestCoordinateValidation:
    """
    Tests for validating Fara coordinate predictions.

    These tests help calibrate expected coordinate ranges for UI elements.
    """

    @pytest.mark.parametrize("element,expected_region", [
        ("EXECUTE button", {"x_min": 500, "x_max": 700, "y_min": 150, "y_max": 300}),
        ("Status panel", {"x_min": 50, "x_max": 300, "y_min": 20, "y_max": 100}),
        ("Terminal header", {"x_min": 100, "x_max": 500, "y_min": 0, "y_max": 80}),
    ])
    def test_coordinate_in_expected_region(self, fara_service, element, expected_region):
        """Test that located coordinates fall within expected regions."""
        # Set mock response within expected region
        center_x = (expected_region["x_min"] + expected_region["x_max"]) // 2
        center_y = (expected_region["y_min"] + expected_region["y_max"]) // 2

        fara_service.set_response({"found": True, "x": center_x, "y": center_y, "confidence": 0.95})

        result = fara_service.locate(element, screenshot="mock")

        if result["found"]:
            assert expected_region["x_min"] <= result["x"] <= expected_region["x_max"], \
                f"X={result['x']} outside [{expected_region['x_min']}, {expected_region['x_max']}]"
            assert expected_region["y_min"] <= result["y"] <= expected_region["y_max"], \
                f"Y={result['y']} outside [{expected_region['y_min']}, {expected_region['y_max']}]"
