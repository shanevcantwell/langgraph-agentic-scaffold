# app/tests/unit/test_fara_service.py
"""
Unit tests for FaraService - Visual UI verification via MCP.

Tests cover:
- Schema validation (LocateResult, VerifyResult, ActionResult)
- MCP function registration
- Screenshot capture (with default/mock)
- Verify element existence
- Locate element coordinates
- Click/type actions
- Error handling for missing dependencies
- Resolution scaling (transparent coordinate transformation)
"""

import pytest
from unittest.mock import MagicMock, patch
import json
import base64
import io

from PIL import Image

from app.src.mcp.services.fara_service import (
    FaraService,
    LocateResult,
    VerifyResult,
    ActionResult,
    DEFAULT_NATIVE_RESOLUTIONS,
)


# =============================================================================
# Test Helpers
# =============================================================================

def create_test_image(width: int, height: int, color: str = "red") -> str:
    """
    Create a test image as base64 PNG.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        color: Fill color name

    Returns:
        Base64-encoded PNG image
    """
    img = Image.new("RGB", (width, height), color=color)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_llm_adapter():
    """Create a mock LLM adapter for Fara-7B."""
    adapter = MagicMock()
    return adapter


@pytest.fixture
def landscape_4k_screenshot():
    """Create a 4K landscape screenshot (3840x2160)."""
    return create_test_image(3840, 2160)


@pytest.fixture
def portrait_screenshot():
    """Create a portrait screenshot (1080x1920)."""
    return create_test_image(1080, 1920)


@pytest.fixture
def square_screenshot():
    """Create a square screenshot (1024x1024)."""
    return create_test_image(1024, 1024)


@pytest.fixture
def mock_browser():
    """Create a mock Playwright page controller."""
    browser = MagicMock()
    browser.screenshot.return_value = b"fake_png_bytes"
    browser.mouse = MagicMock()
    browser.keyboard = MagicMock()
    return browser


@pytest.fixture
def small_test_image():
    """Create a small test image for tests that need valid base64."""
    return create_test_image(100, 100)


@pytest.fixture
def fara_service(mock_llm_adapter, small_test_image):
    """Create a FaraService with mocked dependencies."""
    return FaraService(
        llm_adapter=mock_llm_adapter,
        default_screenshot=small_test_image
    )


@pytest.fixture
def fara_with_browser(mock_llm_adapter, mock_browser):
    """Create a FaraService with browser controller."""
    return FaraService(
        llm_adapter=mock_llm_adapter,
        browser_controller=mock_browser
    )


# =============================================================================
# Schema Tests
# =============================================================================

class TestSchemas:
    """Tests for Fara response schemas."""

    def test_locate_result_found(self):
        """Test LocateResult when element is found."""
        result = LocateResult(
            found=True,
            x=100,
            y=200,
            confidence=0.95,
            description="Submit button"
        )
        assert result.found is True
        assert result.x == 100
        assert result.y == 200
        assert result.confidence == 0.95

    def test_locate_result_not_found(self):
        """Test LocateResult when element not found."""
        result = LocateResult(
            found=False,
            description="Nonexistent element"
        )
        assert result.found is False
        assert result.x is None
        assert result.y is None

    def test_verify_result(self):
        """Test VerifyResult schema."""
        result = VerifyResult(
            exists=True,
            confidence=0.99,
            description="Login button"
        )
        assert result.exists is True
        assert result.confidence == 0.99

    def test_action_result_success(self):
        """Test ActionResult for successful action."""
        result = ActionResult(
            success=True,
            action="click(100, 200)"
        )
        assert result.success is True
        assert result.error is None

    def test_action_result_failure(self):
        """Test ActionResult for failed action."""
        result = ActionResult(
            success=False,
            error="Element not clickable",
            action="click(100, 200)"
        )
        assert result.success is False
        assert "not clickable" in result.error


# =============================================================================
# MCP Registration Tests
# =============================================================================

class TestMcpRegistration:
    """Tests for MCP function registration."""

    def test_get_mcp_functions_returns_dict(self, fara_service):
        """Test that get_mcp_functions returns correct structure."""
        functions = fara_service.get_mcp_functions()

        assert isinstance(functions, dict)
        assert "screenshot" in functions
        assert "verify" in functions
        assert "locate" in functions
        assert "click" in functions
        assert "type" in functions

    def test_mcp_functions_are_callable(self, fara_service):
        """Test that all MCP functions are callable."""
        functions = fara_service.get_mcp_functions()

        for name, func in functions.items():
            assert callable(func), f"Function '{name}' is not callable"


# =============================================================================
# Screenshot Tests
# =============================================================================

class TestScreenshot:
    """Tests for screenshot capture."""

    def test_screenshot_uses_default_when_set(self, fara_service, small_test_image):
        """Test that default_screenshot is returned when set."""
        result = fara_service.screenshot()
        assert result == small_test_image

    def test_screenshot_from_browser(self, fara_with_browser, mock_browser):
        """Test screenshot capture from browser controller."""
        result = fara_with_browser.screenshot()

        mock_browser.screenshot.assert_called_once()
        expected_b64 = base64.b64encode(b"fake_png_bytes").decode("utf-8")
        assert result == expected_b64

    def test_screenshot_raises_without_browser_or_default(self):
        """Test that screenshot raises when no source available."""
        fara = FaraService()  # No browser, no default

        with pytest.raises(ValueError, match="browser_controller"):
            fara.screenshot()


# =============================================================================
# Verify Tests
# =============================================================================

class TestVerify:
    """Tests for element verification."""

    def test_verify_element_found(self, fara_service, mock_llm_adapter, small_test_image):
        """Test verify when element exists."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "confidence": 0.95}'
        }

        result = fara_service.verify("Submit button", screenshot=small_test_image)

        assert result["exists"] is True
        assert result["confidence"] == 0.95
        assert result["description"] == "Submit button"

    def test_verify_element_not_found(self, fara_service, mock_llm_adapter, small_test_image):
        """Test verify when element doesn't exist."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": false, "confidence": 0.1}'
        }

        result = fara_service.verify("Missing element", screenshot=small_test_image)

        assert result["exists"] is False

    def test_verify_captures_screenshot_if_not_provided(self, fara_service, mock_llm_adapter, small_test_image):
        """Test that verify captures screenshot when not provided."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "confidence": 0.9}'
        }

        result = fara_service.verify("Test button")  # No screenshot arg

        # Should have used default_screenshot (scaled to native)
        mock_llm_adapter.invoke.assert_called_once()

    def test_verify_raises_without_adapter(self, small_test_image):
        """Test that verify raises when no LLM adapter."""
        fara = FaraService(default_screenshot=small_test_image)

        with pytest.raises(ValueError, match="llm_adapter"):
            fara.verify("Button")


# =============================================================================
# Locate Tests
# =============================================================================

class TestLocate:
    """Tests for element location."""

    def test_locate_element_found(self, fara_service, mock_llm_adapter, small_test_image):
        """Test locate returns coordinates when found (scaled to original)."""
        # Note: With a 100x100 image, coordinates are scaled from native (1024x1024)
        # Model returns (50, 50) in native -> scales to (50*100/1024, 50*100/1024) ≈ (4, 4)
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "x": 50, "y": 50, "confidence": 0.92}'
        }

        result = fara_service.locate("Execute button", screenshot=small_test_image)

        assert result["found"] is True
        # Coordinates scaled from 1024x1024 native to 100x100 original
        expected_x = int(50 * (100 / 1024))
        expected_y = int(50 * (100 / 1024))
        assert result["x"] == expected_x
        assert result["y"] == expected_y
        assert result["confidence"] == 0.92

    def test_locate_element_not_found(self, fara_service, mock_llm_adapter, small_test_image):
        """Test locate when element doesn't exist."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": false}'
        }

        result = fara_service.locate("Missing element", screenshot=small_test_image)

        assert result["found"] is False
        assert result["x"] is None
        assert result["y"] is None

    def test_locate_handles_markdown_json(self, fara_service, mock_llm_adapter, small_test_image):
        """Test that locate handles JSON wrapped in markdown."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": '```json\n{"found": true, "x": 100, "y": 200}\n```'
        }

        result = fara_service.locate("Button", screenshot=small_test_image)

        assert result["found"] is True
        # Coordinates scaled from 1024x1024 native to 100x100 original
        expected_x = int(100 * (100 / 1024))
        assert result["x"] == expected_x

    def test_locate_handles_extra_text(self, fara_service, mock_llm_adapter, small_test_image):
        """Test that locate extracts JSON from verbose response."""
        mock_llm_adapter.invoke.return_value = {
            "text_response": 'I found the element: {"found": true, "x": 50, "y": 75, "confidence": 0.8} That is my answer.'
        }

        result = fara_service.locate("Icon", screenshot=small_test_image)

        assert result["found"] is True
        # Coordinates scaled from 1024x1024 native to 100x100 original
        expected_x = int(50 * (100 / 1024))
        assert result["x"] == expected_x


# =============================================================================
# Click Tests
# =============================================================================

class TestClick:
    """Tests for click action."""

    def test_click_success(self, fara_with_browser, mock_browser):
        """Test successful click action."""
        result = fara_with_browser.click(100, 200)

        mock_browser.mouse.click.assert_called_once_with(100, 200)
        assert result["success"] is True
        assert "click(100, 200)" in result["action"]

    def test_click_failure(self, fara_with_browser, mock_browser):
        """Test click action failure."""
        mock_browser.mouse.click.side_effect = Exception("Click failed")

        result = fara_with_browser.click(100, 200)

        assert result["success"] is False
        assert "Click failed" in result["error"]

    def test_click_raises_without_browser(self, fara_service):
        """Test that click raises without browser controller."""
        with pytest.raises(ValueError, match="browser_controller"):
            fara_service.click(100, 200)


# =============================================================================
# Type Tests
# =============================================================================

class TestTypeText:
    """Tests for type action."""

    def test_type_success(self, fara_with_browser, mock_browser):
        """Test successful type action."""
        result = fara_with_browser.type_text("Hello World")

        mock_browser.keyboard.type.assert_called_once_with("Hello World")
        assert result["success"] is True

    def test_type_failure(self, fara_with_browser, mock_browser):
        """Test type action failure."""
        mock_browser.keyboard.type.side_effect = Exception("Keyboard error")

        result = fara_with_browser.type_text("Test")

        assert result["success"] is False
        assert "Keyboard error" in result["error"]

    def test_type_raises_without_browser(self, fara_service):
        """Test that type raises without browser controller."""
        with pytest.raises(ValueError, match="browser_controller"):
            fara_service.type_text("Test")


# =============================================================================
# Integration with ReActMixin Tests
# =============================================================================

class TestReActIntegration:
    """Tests for FaraService usage with ReActMixin."""

    def test_locate_then_click_workflow(self, fara_with_browser, mock_llm_adapter, mock_browser, small_test_image):
        """Test typical locate-then-click workflow."""
        # Setup: locate returns coordinates in native space (1024x1024 for square image)
        # These will be scaled to original 100x100 space
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "x": 512, "y": 512, "confidence": 0.97}'
        }

        # Step 1: Locate the element
        locate_result = fara_with_browser.locate(
            "The green EXECUTE button",
            screenshot=small_test_image
        )

        assert locate_result["found"] is True
        x, y = locate_result["x"], locate_result["y"]

        # Coordinates scaled from 1024x1024 to 100x100
        expected_x = int(512 * (100 / 1024))
        expected_y = int(512 * (100 / 1024))

        # Step 2: Click at scaled coordinates
        click_result = fara_with_browser.click(x, y)

        assert click_result["success"] is True
        mock_browser.mouse.click.assert_called_once_with(expected_x, expected_y)

    def test_verify_before_action_workflow(self, fara_with_browser, mock_llm_adapter, small_test_image):
        """Test verify-before-action safety pattern."""
        # Setup: element exists
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "confidence": 0.99}'
        }

        # Verify element exists before proceeding
        verify_result = fara_with_browser.verify(
            "Input field for search",
            screenshot=small_test_image
        )

        assert verify_result["exists"] is True

        # Now safe to type
        type_result = fara_with_browser.type_text("search query")
        assert type_result["success"] is True


# =============================================================================
# Resolution Scaling Tests
# =============================================================================

class TestResolutionScaling:
    """Tests for internal resolution scaling logic."""

    def test_get_image_dimensions(self, mock_llm_adapter):
        """Test that image dimensions are correctly extracted."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Create a 1920x1080 test image
        test_img = create_test_image(1920, 1080)

        width, height = fara._get_image_dimensions(test_img)

        assert width == 1920
        assert height == 1080

    def test_get_image_dimensions_with_data_url(self, mock_llm_adapter):
        """Test dimensions extraction with data URL prefix."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Create image with data URL prefix
        raw_img = create_test_image(800, 600)
        data_url_img = f"data:image/png;base64,{raw_img}"

        width, height = fara._get_image_dimensions(data_url_img)

        assert width == 800
        assert height == 600

    def test_select_best_resolution_landscape(self, mock_llm_adapter):
        """Test that landscape images select landscape resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # 16:9 aspect ratio (landscape)
        result = fara._select_best_resolution(1920, 1080)

        assert result == DEFAULT_NATIVE_RESOLUTIONS["landscape"]

    def test_select_best_resolution_portrait(self, mock_llm_adapter):
        """Test that portrait images select portrait resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # 9:16 aspect ratio (portrait)
        result = fara._select_best_resolution(1080, 1920)

        assert result == DEFAULT_NATIVE_RESOLUTIONS["portrait"]

    def test_select_best_resolution_square(self, mock_llm_adapter):
        """Test that square-ish images select square resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # 1:1 aspect ratio (square)
        result = fara._select_best_resolution(1024, 1024)

        assert result == DEFAULT_NATIVE_RESOLUTIONS["square"]

    def test_scale_to_native(self, mock_llm_adapter):
        """Test that images are scaled to native resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Create a 1920x1080 image
        original = create_test_image(1920, 1080)
        native_res = (1428, 896)

        scaled = fara._scale_to_native(original, native_res)

        # Verify the scaled image has correct dimensions
        scaled_w, scaled_h = fara._get_image_dimensions(scaled)
        assert scaled_w == 1428
        assert scaled_h == 896

    def test_scale_coordinates_2x(self, mock_llm_adapter):
        """Test coordinate scaling with 2x factor."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Native coordinates (500, 300) on 1000x600 native
        # Original is 2000x1200 (2x)
        original_size = (2000, 1200)
        native_size = (1000, 600)

        x, y = fara._scale_coordinates(500, 300, original_size, native_size)

        assert x == 1000  # 500 * 2
        assert y == 600   # 300 * 2

    def test_scale_coordinates_4k_to_native(self, mock_llm_adapter):
        """Test coordinate scaling from native to 4K."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Native coordinates (714, 448) on 1428x896 native
        # Original is 3840x2160 (4K)
        original_size = (3840, 2160)
        native_size = (1428, 896)

        x, y = fara._scale_coordinates(714, 448, original_size, native_size)

        # Expected: 714 * (3840/1428) ≈ 1920, 448 * (2160/896) ≈ 1080
        assert x == int(714 * (3840 / 1428))
        assert y == int(448 * (2160 / 896))

    def test_locate_scales_coordinates_to_original(
        self, mock_llm_adapter, landscape_4k_screenshot
    ):
        """Test that locate returns coordinates in original resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Model returns coordinates in native space (1428x896)
        # Native coordinate (714, 448) is center of 1428x896
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "x": 714, "y": 448, "confidence": 0.95}'
        }

        result = fara.locate("Center element", screenshot=landscape_4k_screenshot)

        assert result["found"] is True
        # Coordinates should be scaled up to 4K space
        # 714 * (3840/1428) ≈ 1920, 448 * (2160/896) ≈ 1080
        expected_x = int(714 * (3840 / 1428))
        expected_y = int(448 * (2160 / 896))
        assert result["x"] == expected_x
        assert result["y"] == expected_y

    def test_locate_with_portrait_image(self, mock_llm_adapter, portrait_screenshot):
        """Test that portrait images use portrait native resolution."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Model returns coordinates in portrait native space (896x1428)
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "x": 448, "y": 714, "confidence": 0.9}'
        }

        result = fara.locate("Button", screenshot=portrait_screenshot)

        assert result["found"] is True
        # Coordinates should be scaled to original portrait (1080x1920)
        expected_x = int(448 * (1080 / 896))
        expected_y = int(714 * (1920 / 1428))
        assert result["x"] == expected_x
        assert result["y"] == expected_y

    def test_custom_native_resolutions(self, mock_llm_adapter, landscape_4k_screenshot):
        """Test that custom native resolutions are respected."""
        custom_resolutions = {
            "square": (512, 512),
            "landscape": (800, 600),
            "portrait": (600, 800),
        }
        fara = FaraService(
            llm_adapter=mock_llm_adapter,
            native_resolutions=custom_resolutions
        )

        # Model returns coordinates in custom native space (800x600)
        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "x": 400, "y": 300, "confidence": 0.95}'
        }

        result = fara.locate("Element", screenshot=landscape_4k_screenshot)

        # Coordinates should be scaled using custom resolution
        expected_x = int(400 * (3840 / 800))
        expected_y = int(300 * (2160 / 600))
        assert result["x"] == expected_x
        assert result["y"] == expected_y

    def test_verify_does_not_return_coordinates(
        self, mock_llm_adapter, landscape_4k_screenshot
    ):
        """Test that verify doesn't include scaled coordinates."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "confidence": 0.95}'
        }

        result = fara.verify("Element exists", screenshot=landscape_4k_screenshot)

        # Verify result doesn't have x/y keys
        assert "x" not in result
        assert "y" not in result
        assert result["exists"] is True

    def test_scaled_image_sent_to_model(self, mock_llm_adapter, landscape_4k_screenshot):
        """Test that the scaled image (not original) is sent to the model."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        mock_llm_adapter.invoke.return_value = {
            "text_response": '{"found": true, "confidence": 0.9}'
        }

        fara.verify("Element", screenshot=landscape_4k_screenshot)

        # Check the image sent to the model
        call_args = mock_llm_adapter.invoke.call_args[0][0]
        sent_image = call_args.image_data

        # The sent image should be scaled to native resolution (1428x896)
        sent_w, sent_h = fara._get_image_dimensions(sent_image)
        native = DEFAULT_NATIVE_RESOLUTIONS["landscape"]
        assert sent_w == native[0]
        assert sent_h == native[1]


# =============================================================================
# Tool Call Parsing Tests (Fara-7B Native Format)
# =============================================================================

class TestToolCallParsing:
    """Tests for parsing Fara-7B's native <tool_call> output format."""

    def test_extract_json_from_tool_call_tags(self, mock_llm_adapter):
        """Test extraction of JSON from <tool_call> tags."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        text = '''I'll click the EXECUTE button to run the command.
<tool_call>
{"name": "computer", "arguments": {"action": "left_click", "coordinate": [624, 280]}}
</tool_call>'''

        result = fara._extract_json(text)

        assert result["found"] is True
        assert result["x"] == 624
        assert result["y"] == 280
        assert result["action"] == "left_click"

    def test_extract_json_tool_call_single_line(self, mock_llm_adapter):
        """Test extraction from single-line tool_call."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        text = '<tool_call>{"name": "computer", "arguments": {"action": "left_click", "coordinate": [100, 200]}}</tool_call>'

        result = fara._extract_json(text)

        assert result["found"] is True
        assert result["x"] == 100
        assert result["y"] == 200

    def test_normalize_tool_call_computer_click(self, mock_llm_adapter):
        """Test normalization of computer tool click action."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        tool_json = {
            "name": "computer",
            "arguments": {
                "action": "left_click",
                "coordinate": [500, 300]
            }
        }

        result = fara._normalize_tool_call(tool_json)

        assert result["found"] is True
        assert result["x"] == 500
        assert result["y"] == 300
        assert result["action"] == "left_click"
        assert result["confidence"] == 1.0

    def test_normalize_tool_call_computer_right_click(self, mock_llm_adapter):
        """Test normalization of right-click action."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        tool_json = {
            "name": "computer",
            "arguments": {
                "action": "right_click",
                "coordinate": [250, 150]
            }
        }

        result = fara._normalize_tool_call(tool_json)

        assert result["found"] is True
        assert result["x"] == 250
        assert result["y"] == 150
        assert result["action"] == "right_click"

    def test_normalize_tool_call_serpico_terminate(self, mock_llm_adapter):
        """Test normalization of serpico terminate action."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        tool_json = {
            "name": "serpico",
            "arguments": {"action": "terminate"}
        }

        result = fara._normalize_tool_call(tool_json)

        assert result["found"] is False
        assert result["action"] == "terminate"

    def test_normalize_tool_call_serpico_with_coordinates(self, mock_llm_adapter):
        """Test normalization of serpico with found + x coordinate array."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Fara sometimes returns coordinates via serpico:
        # {"name": "serpico", "arguments": {"found": true, "x": [614, 280]}}
        tool_json = {
            "name": "serpico",
            "arguments": {"found": True, "x": [614, 280]}
        }

        result = fara._normalize_tool_call(tool_json)

        assert result["found"] is True
        assert result["x"] == 614
        assert result["y"] == 280
        assert result["confidence"] == 1.0

    def test_normalize_tool_call_computer_no_coordinates(self, mock_llm_adapter):
        """Test normalization of computer action without coordinates."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        tool_json = {
            "name": "computer",
            "arguments": {"action": "screenshot"}
        }

        result = fara._normalize_tool_call(tool_json)

        assert result["found"] is True
        assert result["action"] == "screenshot"
        assert "x" not in result
        assert "y" not in result

    def test_normalize_tool_call_unknown_tool(self, mock_llm_adapter):
        """Test normalization of unknown tool returns None."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        tool_json = {
            "name": "unknown_tool",
            "arguments": {"foo": "bar"}
        }

        result = fara._normalize_tool_call(tool_json)

        assert result is None

    def test_extract_json_prefers_tool_call_over_raw_json(self, mock_llm_adapter):
        """Test that <tool_call> format is preferred over raw JSON."""
        fara = FaraService(llm_adapter=mock_llm_adapter)

        # Text with both formats - tool_call should win
        text = '''{"found": false}
<tool_call>
{"name": "computer", "arguments": {"action": "left_click", "coordinate": [100, 100]}}
</tool_call>'''

        result = fara._extract_json(text)

        # Should extract from tool_call, not the raw JSON
        assert result["found"] is True
        assert result["x"] == 100
        assert result["y"] == 100

    def test_locate_handles_tool_call_format(
        self, mock_llm_adapter, small_test_image
    ):
        """Test that locate() handles Fara's native tool_call format end-to-end."""
        fara = FaraService(
            llm_adapter=mock_llm_adapter,
            default_screenshot=small_test_image
        )

        # Fara returns tool_call format (coordinates in native space)
        mock_llm_adapter.invoke.return_value = {
            "text_response": '''<tool_call>
{"name": "computer", "arguments": {"action": "left_click", "coordinate": [512, 512]}}
</tool_call>'''
        }

        result = fara.locate("Execute button", screenshot=small_test_image)

        assert result["found"] is True
        # Coordinates scaled from 1024x1024 native to 100x100 original
        expected_x = int(512 * (100 / 1024))
        expected_y = int(512 * (100 / 1024))
        assert result["x"] == expected_x
        assert result["y"] == expected_y

    def test_verify_handles_serpico_terminate(
        self, mock_llm_adapter, small_test_image
    ):
        """Test that verify() handles serpico terminate as 'not found'."""
        fara = FaraService(
            llm_adapter=mock_llm_adapter,
            default_screenshot=small_test_image
        )

        # Fara returns serpico terminate when it can't find element
        mock_llm_adapter.invoke.return_value = {
            "text_response": '''I cannot find that element.
<tool_call>
{"name": "serpico", "arguments": {"action": "terminate"}}
</tool_call>'''
        }

        result = fara.verify("Missing element", screenshot=small_test_image)

        assert result["exists"] is False
