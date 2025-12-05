# app/src/mcp/services/visual_browser_service.py
"""
VisualBrowserService - Fara-driven Playwright browser automation.

Combines Fara's visual understanding with Playwright's browser control
for visually-driven web interaction. Unlike DOM-based automation, this
service locates elements by description ("the submit button") rather
than selectors ("button.submit-btn").

Architecture:
    ┌─────────────────┐
    │  Specialist     │  "click the login button"
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ VisualBrowser   │  Coordinates Fara + Playwright
    │    Service      │
    └────────┬────────┘
             │
      ┌──────┴──────┐
      ▼             ▼
┌──────────┐  ┌──────────┐
│  Fara    │  │Playwright│
│ (vision) │  │ (action) │
└──────────┘  └──────────┘
      │             │
      └──────┬──────┘
             ▼
        [Browser]

Usage:
    # Create service
    browser = VisualBrowserService(fara_adapter=fara_llm)

    # Navigate and interact visually
    await browser.navigate("https://example.com")
    await browser.visual_click("The blue Sign In button")
    await browser.visual_type("Email input field", "user@example.com")

    # Get current state
    screenshot = await browser.screenshot()

    # Register with MCP
    registry.register_service("visual_browser", browser.get_mcp_functions())
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, TYPE_CHECKING

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from .fara_service import FaraService

if TYPE_CHECKING:
    from ...llm.adapter import BaseAdapter

logger = logging.getLogger(__name__)


@dataclass
class VisualBrowserService:
    """
    MCP service for visually-driven browser automation.

    Combines Fara (visual AI) with Playwright (browser automation) to enable
    natural language element interaction without DOM selectors.

    Attributes:
        fara_adapter: LLM adapter configured for Fara-7B
        headless: Run browser without visible window (default: True)
        viewport: Browser viewport size as (width, height)
        timeout_ms: Default timeout for operations in milliseconds
    """
    fara_adapter: Optional["BaseAdapter"] = None
    headless: bool = True
    viewport: tuple = (1920, 1080)
    timeout_ms: int = 30000

    # Internal state (initialized on first use)
    _playwright: Any = field(default=None, repr=False)
    _browser: Optional[Browser] = field(default=None, repr=False)
    _context: Optional[BrowserContext] = field(default=None, repr=False)
    _page: Optional[Page] = field(default=None, repr=False)
    _fara: Optional[FaraService] = field(default=None, repr=False)

    def __post_init__(self):
        """Initialize Fara service with shared adapter."""
        if self.fara_adapter:
            self._fara = FaraService(llm_adapter=self.fara_adapter)

    def get_mcp_functions(self) -> Dict[str, callable]:
        """
        Returns dict of functions to register with MCP registry.

        Usage:
            registry.register_service("visual_browser", browser.get_mcp_functions())
        """
        return {
            "launch": self.launch,
            "navigate": self.navigate,
            "screenshot": self.screenshot,
            "visual_click": self.visual_click,
            "visual_type": self.visual_type,
            "visual_verify": self.visual_verify,
            "close": self.close,
            "current_url": self.current_url,
            "page_title": self.page_title,
        }

    # =========================================================================
    # Lifecycle
    # =========================================================================

    async def launch(self, browser_type: str = "chromium") -> Dict[str, Any]:
        """
        Launch browser instance.

        Args:
            browser_type: "chromium", "firefox", or "webkit"

        Returns:
            Dict with success status and browser info
        """
        if self._browser:
            logger.warning("VisualBrowserService: Browser already launched")
            return {"success": True, "status": "already_running"}

        logger.info(f"VisualBrowserService: Launching {browser_type} (headless={self.headless})")

        try:
            self._playwright = await async_playwright().start()

            browser_launcher = getattr(self._playwright, browser_type)
            self._browser = await browser_launcher.launch(headless=self.headless)

            self._context = await self._browser.new_context(
                viewport={"width": self.viewport[0], "height": self.viewport[1]}
            )
            self._page = await self._context.new_page()

            # Wire Fara to use this page for screenshots
            if self._fara:
                self._fara.browser_controller = self._page

            logger.info("VisualBrowserService: Browser launched successfully")
            return {
                "success": True,
                "browser": browser_type,
                "viewport": self.viewport,
                "headless": self.headless
            }

        except Exception as e:
            logger.error(f"VisualBrowserService: Launch failed: {e}")
            return {"success": False, "error": str(e)}

    async def close(self) -> Dict[str, Any]:
        """
        Close browser and cleanup resources.

        Returns:
            Dict with success status
        """
        logger.info("VisualBrowserService: Closing browser")

        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

            if self._fara:
                self._fara.browser_controller = None

            return {"success": True}

        except Exception as e:
            logger.error(f"VisualBrowserService: Close failed: {e}")
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Navigation
    # =========================================================================

    async def navigate(self, url: str, wait_until: str = "networkidle") -> Dict[str, Any]:
        """
        Navigate to URL and wait for page load.

        Args:
            url: URL to navigate to
            wait_until: "load", "domcontentloaded", "networkidle", or "commit"

        Returns:
            Dict with success status, final URL, and page title
        """
        self._ensure_browser()

        logger.info(f"VisualBrowserService: Navigating to {url}")

        try:
            response = await self._page.goto(
                url,
                wait_until=wait_until,
                timeout=self.timeout_ms
            )

            return {
                "success": True,
                "url": self._page.url,
                "title": await self._page.title(),
                "status": response.status if response else None
            }

        except Exception as e:
            logger.error(f"VisualBrowserService: Navigation failed: {e}")
            return {"success": False, "error": str(e), "url": url}

    async def current_url(self) -> str:
        """Get current page URL."""
        self._ensure_browser()
        return self._page.url

    async def page_title(self) -> str:
        """Get current page title."""
        self._ensure_browser()
        return await self._page.title()

    # =========================================================================
    # Visual Interaction (Fara-driven)
    # =========================================================================

    async def screenshot(self, full_page: bool = False) -> str:
        """
        Capture current page as base64 PNG.

        Args:
            full_page: Capture full scrollable page (default: viewport only)

        Returns:
            Base64-encoded PNG screenshot
        """
        self._ensure_browser()

        screenshot_bytes = await self._page.screenshot(full_page=full_page)
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def visual_click(
        self,
        description: str,
        screenshot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Click an element by visual description.

        Uses Fara to locate the element, then Playwright to click.

        Args:
            description: Natural language description of element
                         e.g., "The blue Sign In button"
            screenshot: Optional pre-captured screenshot (captures if None)

        Returns:
            Dict with success, coordinates clicked, and Fara's locate result

        Example:
            result = await browser.visual_click("Submit button")
            if result["success"]:
                print(f"Clicked at ({result['x']}, {result['y']})")
        """
        self._ensure_browser()
        self._ensure_fara()

        logger.info(f"VisualBrowserService.visual_click: '{description}'")

        # Get screenshot if not provided
        if not screenshot:
            screenshot = await self.screenshot()

        # Use Fara to locate element
        locate_result = self._fara.locate(description, screenshot)

        if not locate_result.get("found"):
            logger.warning(f"VisualBrowserService: Element not found: '{description}'")
            return {
                "success": False,
                "error": f"Element not found: {description}",
                "locate_result": locate_result
            }

        x, y = locate_result["x"], locate_result["y"]

        # Click at coordinates
        try:
            await self._page.mouse.click(x, y)
            logger.info(f"VisualBrowserService: Clicked at ({x}, {y})")

            # Small delay for UI to respond
            await asyncio.sleep(0.3)

            return {
                "success": True,
                "x": x,
                "y": y,
                "description": description,
                "confidence": locate_result.get("confidence")
            }

        except Exception as e:
            logger.error(f"VisualBrowserService: Click failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "x": x,
                "y": y
            }

    async def visual_type(
        self,
        description: str,
        text: str,
        clear_first: bool = True,
        screenshot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Type into an element located by visual description.

        Args:
            description: Natural language description of input element
                         e.g., "Email input field"
            text: Text to type
            clear_first: Clear existing content before typing (default: True)
            screenshot: Optional pre-captured screenshot

        Returns:
            Dict with success status and action details
        """
        self._ensure_browser()
        self._ensure_fara()

        logger.info(f"VisualBrowserService.visual_type: '{description}' <- '{text[:20]}...'")

        # Click to focus the element first
        click_result = await self.visual_click(description, screenshot)

        if not click_result.get("success"):
            return {
                "success": False,
                "error": f"Could not click input: {click_result.get('error')}",
                "description": description
            }

        try:
            # Clear existing content if requested
            if clear_first:
                await self._page.keyboard.press("Control+a")
                await self._page.keyboard.press("Backspace")

            # Type the text
            await self._page.keyboard.type(text, delay=50)  # Human-like typing

            return {
                "success": True,
                "description": description,
                "text_length": len(text),
                "cleared": clear_first
            }

        except Exception as e:
            logger.error(f"VisualBrowserService: Type failed: {e}")
            return {"success": False, "error": str(e)}

    async def visual_verify(
        self,
        description: str,
        screenshot: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify an element exists by visual description.

        Args:
            description: Natural language description of element
            screenshot: Optional pre-captured screenshot

        Returns:
            Dict with exists (bool), confidence, and description
        """
        self._ensure_browser()
        self._ensure_fara()

        if not screenshot:
            screenshot = await self.screenshot()

        return self._fara.verify(description, screenshot)

    # =========================================================================
    # Utility
    # =========================================================================

    def _ensure_browser(self):
        """Raise if browser not launched."""
        if not self._page:
            raise RuntimeError(
                "Browser not launched. Call launch() first."
            )

    def _ensure_fara(self):
        """Raise if Fara not configured."""
        if not self._fara or not self._fara.llm_adapter:
            raise RuntimeError(
                "Fara not configured. Provide fara_adapter on init."
            )

    # =========================================================================
    # Context Manager Support
    # =========================================================================

    async def __aenter__(self):
        """Async context manager entry - launches browser."""
        await self.launch()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes browser."""
        await self.close()
        return False
