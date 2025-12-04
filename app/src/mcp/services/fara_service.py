# app/src/mcp/services/fara_service.py
"""
FaraService - Visual UI verification using Fara-7B vision model.

Fara-7B is Microsoft's 7B parameter vision model for computer use.
It takes screenshots and predicts UI element coordinates from natural
language descriptions, enabling:
  - Element verification (does this exist?)
  - Element location (where is this?)
  - Click/type actions via Playwright

This is an MCP service, not a specialist. It provides tool capabilities
that specialists can invoke via the ReActMixin:

    tools = {
        "screenshot": ToolDef(service="fara", function="screenshot"),
        "verify": ToolDef(service="fara", function="verify"),
        "locate": ToolDef(service="fara", function="locate"),
        "click": ToolDef(service="fara", function="click"),
        "type": ToolDef(service="fara", function="type"),
    }

Design:
  - Fara-7B runs locally via LM Studio (GGUF format)
  - Playwright handles browser automation
  - Service is stateful (holds browser context)
  - Thread-safe for concurrent ReAct loops
  - Resolution scaling is INTERNAL - callers work in original coordinates

Resolution Scaling:
  Vision models have native input resolutions. This service handles scaling
  transparently:
  1. Caller passes original screenshot (e.g., 4K 3840x2160)
  2. Service scales DOWN to model's native resolution (e.g., 1428x896)
  3. Model returns coordinates in native space
  4. Service scales coordinates UP to original space
  5. Caller receives coordinates in original resolution

  Native resolutions are configurable per aspect ratio:
    native_resolutions:
      square: [1024, 1024]
      landscape: [1428, 896]
      portrait: [896, 1428]

Prerequisites:
  - Fara-7B GGUF loaded in LM Studio
  - LM Studio server running (default: http://localhost:1234)
  - Playwright browser installed (optional, for automation)
"""

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from pydantic import BaseModel, Field
from PIL import Image

if TYPE_CHECKING:
    from ...llm.adapter import BaseAdapter

logger = logging.getLogger(__name__)


# =============================================================================
# Default Native Resolutions
# =============================================================================

DEFAULT_NATIVE_RESOLUTIONS = {
    "square": (1024, 1024),
    "landscape": (1428, 896),
    "portrait": (896, 1428),
}


# =============================================================================
# Response Schemas
# =============================================================================

class LocateResult(BaseModel):
    """Result of locating a UI element."""
    found: bool = Field(..., description="Whether the element was found")
    x: Optional[int] = Field(None, description="X coordinate (center of element)")
    y: Optional[int] = Field(None, description="Y coordinate (center of element)")
    confidence: Optional[float] = Field(None, description="Model confidence 0-1")
    description: str = Field(..., description="Element description that was searched")


class VerifyResult(BaseModel):
    """Result of verifying a UI element exists."""
    exists: bool = Field(..., description="Whether the element exists")
    confidence: Optional[float] = Field(None, description="Model confidence 0-1")
    description: str = Field(..., description="Element description that was verified")


class ActionResult(BaseModel):
    """Result of a click/type action."""
    success: bool = Field(..., description="Whether the action succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    action: str = Field(..., description="Action that was performed")


# =============================================================================
# FaraService
# =============================================================================

@dataclass
class FaraService:
    """
    MCP service for visual UI verification using Fara-7B.

    Attributes:
        llm_adapter: LLM adapter configured for Fara-7B (injected)
        browser_controller: Optional Playwright controller for automation
        default_screenshot: Optional default screenshot for testing
        native_resolutions: Dict mapping aspect ratio names to (width, height)

    Example:
        # Create service with Fara-7B adapter and custom resolutions
        fara = FaraService(
            llm_adapter=fara_adapter,
            native_resolutions={
                "square": (1024, 1024),
                "landscape": (1428, 896),
                "portrait": (896, 1428),
            }
        )

        # Register with MCP
        registry.register_service("fara", fara.get_mcp_functions())

        # Callers work in original coordinates - scaling is transparent
        # mcp_client.call("fara", "locate", screenshot=b64_4k, description="Submit button")
        # Returns coordinates in 4K space, not model's native space
    """
    llm_adapter: Optional["BaseAdapter"] = None
    browser_controller: Optional[Any] = None  # Playwright Page instance
    default_screenshot: Optional[str] = None  # For testing
    native_resolutions: Dict[str, Tuple[int, int]] = field(
        default_factory=lambda: DEFAULT_NATIVE_RESOLUTIONS.copy()
    )

    def get_mcp_functions(self) -> Dict[str, callable]:
        """
        Returns dict of functions to register with MCP registry.

        Usage:
            registry.register_service("fara", fara.get_mcp_functions())
        """
        return {
            "screenshot": self.screenshot,
            "verify": self.verify,
            "locate": self.locate,
            "click": self.click,
            "type": self.type_text,
        }

    # =========================================================================
    # Core MCP Functions
    # =========================================================================

    def screenshot(self) -> str:
        """
        Capture current browser state as base64 PNG.

        Returns:
            Base64-encoded PNG screenshot

        Raises:
            ValueError: If no browser controller attached

        Note:
            Returns default_screenshot if set (for testing without browser)
        """
        if self.default_screenshot:
            logger.debug("FaraService.screenshot: Using default screenshot")
            return self.default_screenshot

        if not self.browser_controller:
            raise ValueError(
                "FaraService.screenshot requires browser_controller. "
                "Either attach a Playwright page or set default_screenshot for testing."
            )

        logger.info("FaraService: Capturing screenshot")

        try:
            # Playwright screenshot returns bytes
            screenshot_bytes = self.browser_controller.screenshot()
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")
            logger.debug(f"FaraService: Screenshot captured ({len(b64)} chars)")
            return b64
        except Exception as e:
            logger.error(f"FaraService.screenshot failed: {e}")
            raise ValueError(f"Screenshot capture failed: {e}")

    def verify(self, description: str, screenshot: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify that a UI element exists in the screenshot.

        Args:
            description: Natural language description of the element
                         e.g., "The green EXECUTE button"
            screenshot: Base64-encoded screenshot. If None, captures one.

        Returns:
            Dict with keys: exists (bool), confidence (float), description (str)

        Example:
            result = fara.verify("Submit button", screenshot=b64)
            if result["exists"]:
                print("Button found!")
        """
        if not self.llm_adapter:
            raise ValueError("FaraService.verify requires llm_adapter to be set")

        # Get screenshot if not provided
        if not screenshot:
            screenshot = self.screenshot()

        logger.info(f"FaraService.verify: '{description}'")

        # Call Fara-7B (scaling handled internally)
        result = self._invoke_fara(
            screenshot=screenshot,
            task="verify",
            description=description
        )

        return VerifyResult(
            exists=result.get("found", False),
            confidence=result.get("confidence"),
            description=description
        ).model_dump()

    def locate(self, description: str, screenshot: Optional[str] = None) -> Dict[str, Any]:
        """
        Locate a UI element and return its coordinates.

        Coordinates are returned in the ORIGINAL screenshot's resolution.
        Scaling to/from the model's native resolution is handled internally.

        Args:
            description: Natural language description of the element
                         e.g., "The green EXECUTE button"
            screenshot: Base64-encoded screenshot. If None, captures one.

        Returns:
            Dict with keys: found (bool), x (int), y (int), confidence (float)
            Coordinates are in original screenshot space.

        Example:
            # 4K screenshot (3840x2160)
            result = fara.locate("Submit button", screenshot=b64_4k)
            if result["found"]:
                # x, y are in 4K coordinates, not model's native 1428x896
                print(f"Button at ({result['x']}, {result['y']})")
        """
        if not self.llm_adapter:
            raise ValueError("FaraService.locate requires llm_adapter to be set")

        # Get screenshot if not provided
        if not screenshot:
            screenshot = self.screenshot()

        logger.info(f"FaraService.locate: '{description}'")

        # Call Fara-7B (scaling handled internally, coordinates returned in original space)
        result = self._invoke_fara(
            screenshot=screenshot,
            task="locate",
            description=description
        )

        return LocateResult(
            found=result.get("found", False),
            x=result.get("x"),
            y=result.get("y"),
            confidence=result.get("confidence"),
            description=description
        ).model_dump()

    def click(self, x: int, y: int) -> Dict[str, Any]:
        """
        Click at the specified coordinates.

        Args:
            x: X coordinate (pixels from left)
            y: Y coordinate (pixels from top)

        Returns:
            Dict with keys: success (bool), error (str|None), action (str)

        Raises:
            ValueError: If no browser controller attached
        """
        if not self.browser_controller:
            raise ValueError(
                "FaraService.click requires browser_controller. "
                "Attach a Playwright page to enable browser automation."
            )

        logger.info(f"FaraService.click: ({x}, {y})")

        try:
            self.browser_controller.mouse.click(x, y)
            return ActionResult(
                success=True,
                action=f"click({x}, {y})"
            ).model_dump()
        except Exception as e:
            logger.error(f"FaraService.click failed: {e}")
            return ActionResult(
                success=False,
                error=str(e),
                action=f"click({x}, {y})"
            ).model_dump()

    def type_text(self, text: str) -> Dict[str, Any]:
        """
        Type text into the currently focused element.

        Args:
            text: Text to type

        Returns:
            Dict with keys: success (bool), error (str|None), action (str)

        Raises:
            ValueError: If no browser controller attached
        """
        if not self.browser_controller:
            raise ValueError(
                "FaraService.type requires browser_controller. "
                "Attach a Playwright page to enable browser automation."
            )

        logger.info(f"FaraService.type: '{text[:50]}...' ({len(text)} chars)")

        try:
            self.browser_controller.keyboard.type(text)
            return ActionResult(
                success=True,
                action=f"type({len(text)} chars)"
            ).model_dump()
        except Exception as e:
            logger.error(f"FaraService.type failed: {e}")
            return ActionResult(
                success=False,
                error=str(e),
                action=f"type({len(text)} chars)"
            ).model_dump()

    # =========================================================================
    # Resolution Scaling (Internal)
    # =========================================================================

    def _get_image_dimensions(self, b64_image: str) -> Tuple[int, int]:
        """
        Get dimensions of a base64-encoded image.

        Args:
            b64_image: Base64-encoded image data

        Returns:
            Tuple of (width, height)
        """
        # Handle data URL prefix if present
        if "," in b64_image:
            b64_image = b64_image.split(",", 1)[1]

        img_bytes = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_bytes))
        return img.size  # (width, height)

    def _select_best_resolution(self, width: int, height: int) -> Tuple[int, int]:
        """
        Select the best native resolution based on input aspect ratio.

        Args:
            width: Original image width
            height: Original image height

        Returns:
            Best matching (native_width, native_height) from configured resolutions
        """
        aspect_ratio = width / height

        # Classify aspect ratio
        if aspect_ratio > 1.2:
            # Landscape
            return self.native_resolutions.get("landscape", (1428, 896))
        elif aspect_ratio < 0.8:
            # Portrait
            return self.native_resolutions.get("portrait", (896, 1428))
        else:
            # Square-ish
            return self.native_resolutions.get("square", (1024, 1024))

    def _scale_to_native(self, b64_image: str, native_res: Tuple[int, int]) -> str:
        """
        Scale image down to native resolution.

        Args:
            b64_image: Base64-encoded original image
            native_res: Target (width, height)

        Returns:
            Base64-encoded scaled image
        """
        # Handle data URL prefix
        prefix = ""
        if "," in b64_image:
            prefix, b64_image = b64_image.split(",", 1)
            prefix += ","

        img_bytes = base64.b64decode(b64_image)
        img = Image.open(io.BytesIO(img_bytes))

        # Resize with high-quality resampling
        scaled = img.resize(native_res, Image.LANCZOS)

        # Encode back to base64 PNG
        buffer = io.BytesIO()
        scaled.save(buffer, format="PNG")
        scaled_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return prefix + scaled_b64

    def _scale_coordinates(
        self,
        x: int,
        y: int,
        original_size: Tuple[int, int],
        native_size: Tuple[int, int]
    ) -> Tuple[int, int]:
        """
        Scale coordinates from native resolution back to original.

        Args:
            x: X coordinate in native space
            y: Y coordinate in native space
            original_size: (original_width, original_height)
            native_size: (native_width, native_height)

        Returns:
            (x, y) scaled to original resolution
        """
        scale_x = original_size[0] / native_size[0]
        scale_y = original_size[1] / native_size[1]

        return (int(x * scale_x), int(y * scale_y))

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _invoke_fara(
        self,
        screenshot: str,
        task: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Invoke Fara-7B model for visual understanding.

        Handles resolution scaling internally:
        1. Gets original image dimensions
        2. Selects best native resolution based on aspect ratio
        3. Scales image down to native resolution
        4. Invokes model
        5. Scales coordinates back up (for locate task)

        Args:
            screenshot: Base64-encoded screenshot (original resolution)
            task: "verify" or "locate"
            description: Natural language description of target element

        Returns:
            Dict with model response (coordinates in original resolution):
            - For verify: {"found": bool, "confidence": float}
            - For locate: {"found": bool, "x": int, "y": int, "confidence": float}
        """
        from ...llm.adapter import StandardizedLLMRequest
        from langchain_core.messages import HumanMessage, SystemMessage

        # Step 1: Get original dimensions
        original_size = self._get_image_dimensions(screenshot)
        logger.debug(f"FaraService: Original image size: {original_size}")

        # Step 2: Select best native resolution
        native_size = self._select_best_resolution(*original_size)
        logger.debug(f"FaraService: Selected native resolution: {native_size}")

        # Step 3: Scale down to native resolution
        scaled_screenshot = self._scale_to_native(screenshot, native_size)
        logger.debug(f"FaraService: Scaled image for model")

        # Build Fara-7B specific prompt
        # TODO: Adjust based on actual Fara-7B prompt format
        if task == "verify":
            prompt = f"Does this UI contain: {description}? Answer with JSON: {{\"found\": true/false, \"confidence\": 0.0-1.0}}"
        elif task == "locate":
            prompt = f"Locate the UI element: {description}. Answer with JSON: {{\"found\": true/false, \"x\": pixels, \"y\": pixels, \"confidence\": 0.0-1.0}}"
        else:
            raise ValueError(f"Unknown Fara task: {task}")

        system_prompt = (
            "You are Fara, a vision model for computer use. "
            "Analyze the screenshot and respond with the requested JSON format only."
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt)
        ]

        request = StandardizedLLMRequest(
            messages=messages,
            image_data=scaled_screenshot  # Send scaled image to model
        )

        logger.debug(f"FaraService._invoke_fara: task={task}, description='{description}'")

        try:
            response = self.llm_adapter.invoke(request)
            text = response.get("text_response", "")

            # Parse JSON response
            import json
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                result = self._extract_json(text)

            # Step 5: Scale coordinates back to original resolution (for locate)
            if task == "locate" and result.get("found") and result.get("x") is not None:
                native_x = result["x"]
                native_y = result["y"]
                original_x, original_y = self._scale_coordinates(
                    native_x, native_y, original_size, native_size
                )
                result["x"] = original_x
                result["y"] = original_y
                logger.debug(
                    f"FaraService: Scaled coordinates ({native_x}, {native_y}) -> "
                    f"({original_x}, {original_y})"
                )

            logger.debug(f"FaraService._invoke_fara result: {result}")
            return result

        except Exception as e:
            logger.error(f"FaraService._invoke_fara failed: {e}")
            return {"found": False, "error": str(e)}

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Extract JSON from model response text.

        Handles cases where model wraps JSON in markdown or adds explanation.
        """
        import json
        import re

        # Try markdown code block
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { to last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass

        # Fallback: return not found
        logger.warning(f"FaraService._extract_json: Could not parse: {text[:200]}")
        return {"found": False, "error": "Could not parse model response"}
