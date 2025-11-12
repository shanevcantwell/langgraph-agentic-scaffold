"""
Gemini Web UI Adapter using Playwright for browser automation.

This adapter extracts thinking blocks from Gemini's web UI since they're not exposed
via the API. It uses Pydantic schemas for fail-fast validation when UI structure changes.

Reference: docs/ADR/ADR-DISTILL-006_GeminiWebUI_Adapter.md
Reference Implementation: /home/shane/github/shanevcantwell/gemini-exporter/content.js

Performance Characteristics:
- Speed: ~3-5 seconds per request (vs <1s for API)
- Memory: ~200-400 MB for headless Chrome
- Throughput: ~20-30 requests per minute (with rate limiting)

IMPORTANT: This is temporary infrastructure for distillation data capture.
Not intended for long-term production use.
"""

import logging
import time
import re
import json
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Page, Browser, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from pydantic import ValidationError

from .adapter import BaseAdapter, StandardizedLLMRequest
from .gemini_webui_schemas import GeminiUIResponse, ThinkingStage
from ..utils.errors import LLMInvocationError

logger = logging.getLogger(__name__)


class GeminiWebUIAdapter(BaseAdapter):
    """
    Adapter for Gemini web UI using browser automation.
    Extracts thinking blocks via DOM scraping (like gemini-exporter).
    Uses Pydantic schemas for fail-fast validation when UI structure changes.

    Reference Implementation: /home/shane/github/shanevcantwell/gemini-exporter/content.js
    """

    def __init__(
        self,
        model_config: Dict[str, Any],
        credentials: Dict[str, Any],
        system_prompt: str
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is not installed. Install with: pip install playwright && "
                "playwright install chromium"
            )

        super().__init__(model_config)
        self.session_cookies_path = credentials.get("session_cookies")
        self.rate_limit_delay = model_config.get("rate_limit_delay", 2.0)
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright: Optional[Playwright] = None

    @property
    def api_base(self) -> Optional[str]:
        """Web UI URL"""
        return "https://gemini.google.com"

    @property
    def api_key(self) -> Optional[str]:
        """No API key for web UI adapter"""
        return None

    @classmethod
    def from_config(
        cls,
        provider_config: Dict[str, Any],
        system_prompt: str
    ) -> "GeminiWebUIAdapter":
        """Factory method for adapter creation"""
        model_config = {
            "api_identifier": "gemini-2.0-flash-thinking-webui",
            "parameters": provider_config.get("parameters", {}),
            "rate_limit_delay": provider_config.get("rate_limit_delay", 2.0),
        }
        credentials = {
            "session_cookies": provider_config.get("session_cookies"),
        }
        return cls(model_config, credentials, system_prompt)

    def invoke(self, request: StandardizedLLMRequest) -> Dict[str, Any]:
        """
        Submit prompt to Gemini web UI and extract response + thinking.

        Args:
            request: StandardizedLLMRequest with messages

        Returns:
            Dict with text_response and thinking_stages

        Raises:
            LLMInvocationError: If DOM extraction fails or validation fails
        """
        prompt_text = request.messages[-1].content
        logger.info(f"GeminiWebUIAdapter: Submitting prompt ({len(prompt_text)} chars)")

        # Initialize browser if needed
        if not self.page:
            self._initialize_browser()

        try:
            # Submit prompt and wait for response
            self._submit_prompt(prompt_text)
            self._wait_for_response_complete()

            # Rate limiting (mimic human interaction)
            time.sleep(self.rate_limit_delay)

            # Extract and validate using Pydantic schema
            ui_response = self._extract_and_validate()

            # Return standardized format
            return {
                "text_response": ui_response.container.response_text,
                "thinking_stages": (
                    [stage.model_dump() for stage in ui_response.container.thinking.stages]
                    if ui_response.container.thinking
                    else None
                ),
            }

        except ValidationError as e:
            logger.error(f"Gemini UI structure changed, validation failed: {e}")
            logger.error("DOM selectors may need updating in gemini_webui_adapter.py")
            raise LLMInvocationError(f"DOM extraction failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error in GeminiWebUIAdapter: {e}", exc_info=True)
            raise LLMInvocationError(f"Web UI automation failed: {e}") from e

    def _initialize_browser(self):
        """
        Initialize Playwright browser and restore session.

        Mirrors gemini-exporter's approach but uses server-side Playwright
        instead of Chrome extension.
        """
        logger.info("Initializing Playwright browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,  # Run without visible window
            args=[
                "--disable-blink-features=AutomationControlled",  # Avoid detection
            ],
        )

        # Create browser context with session cookies
        context = self.browser.new_context()
        if self.session_cookies_path:
            cookies_path = Path(self.session_cookies_path)
            if cookies_path.exists():
                with open(cookies_path, 'r') as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                logger.info("Restored session from cookies")
            else:
                logger.warning(f"Session cookies file not found: {self.session_cookies_path}")

        self.page = context.new_page()
        self.page.goto("https://gemini.google.com/app")
        logger.info("Browser initialized and navigated to Gemini")

        # Wait for page load
        self.page.wait_for_load_state("networkidle")

    def _submit_prompt(self, prompt_text: str):
        """
        Submit prompt to Gemini web UI.

        Mirrors content.js prompt submission logic.
        """
        # Find textarea input (may need selector adjustment)
        textarea = self.page.wait_for_selector("textarea", timeout=10000)
        textarea.fill(prompt_text)

        # Click send button (selector may need adjustment)
        send_button = self.page.wait_for_selector(
            'button[aria-label*="Send"], button[type="submit"]',
            timeout=5000
        )
        send_button.click()
        logger.debug("Prompt submitted")

    def _wait_for_response_complete(self):
        """
        Wait for Gemini to finish generating response.

        Mirrors content.js waiting logic - wait for streaming to stop.
        """
        # Wait for new conversation container to appear
        self.page.wait_for_selector(".conversation-container:last-child", timeout=60000)

        # Wait for response streaming to complete
        # Strategy: Wait for "Stop generating" button to disappear
        try:
            stop_button = self.page.wait_for_selector(
                'button[aria-label*="Stop"]',
                timeout=5000
            )
            # Wait for it to disappear (response complete)
            stop_button.wait_for(state="detached", timeout=120000)
        except:
            # No stop button found, response likely already complete
            pass

        # Additional wait for rendering to stabilize
        time.sleep(2)
        logger.debug("Response generation complete")

    def _expand_thinking_blocks(self):
        """
        Click 'Show thinking' buttons and wait for expansion.

        Mirrors content.js expandThinkingBlocks() function (lines 700-805).
        Multi-pass expansion with retry logic.
        """
        max_passes = 10
        expanded_count = 0

        for pass_num in range(1, max_passes + 1):
            # Find all 'Show thinking' buttons
            buttons = self.page.query_selector_all(
                'button[data-test-id="thoughts-header-button"]'
            )

            unexpanded = [
                btn for btn in buttons
                if "Show thinking" in btn.inner_text().lower()
            ]

            if not unexpanded:
                logger.debug(
                    f"Thinking block expansion complete after {pass_num} passes. "
                    f"Expanded {expanded_count} blocks."
                )
                break

            logger.debug(
                f"Pass {pass_num}: Found {len(unexpanded)} unexpanded thinking blocks"
            )

            for button in unexpanded:
                try:
                    # Scroll into view and click
                    button.scroll_into_view_if_needed()
                    button.click()
                    expanded_count += 1

                    # Verify expansion (retry up to 10 times, like gemini-exporter)
                    verified = False
                    for retry in range(10):
                        time.sleep(0.5)
                        # Check if content appeared
                        thinking_content = self.page.query_selector(
                            '[class*="model-thoughts"], [class*="thinking"]'
                        )
                        if thinking_content and len(thinking_content.inner_text()) > 50:
                            verified = True
                            break

                    if not verified:
                        logger.warning(f"Failed to verify thinking block expansion")

                except Exception as e:
                    logger.warning(f"Error expanding thinking button: {e}")
                    continue

            # Wait before next pass
            time.sleep(1)

    def _extract_and_validate(self) -> GeminiUIResponse:
        """
        Extract DOM data and validate against Pydantic schema.

        This is the main extraction orchestrator. Mirrors content.js
        extractStructuredConversation() function (lines 888-1118).

        Returns:
            Validated GeminiUIResponse

        Raises:
            ValidationError: If DOM structure doesn't match schema
        """
        # Step 1: Expand thinking blocks
        self._expand_thinking_blocks()

        # Step 2: Get most recent conversation container
        container = self.page.query_selector(".conversation-container:last-child")
        if not container:
            raise LLMInvocationError("No conversation container found")

        # Step 3: Extract all fields
        data = {
            "conversation_id": self._extract_conversation_id(),
            "container": {
                "container_id": container.get_attribute("id"),
                "user_text": self._extract_user_text(container),
                "thinking": self._extract_thinking(container),
                "response_text": self._extract_response_text(container),
            },
        }

        # Step 4: Validate with Pydantic - fails fast if structure changed
        return GeminiUIResponse(**data)

    def _extract_conversation_id(self) -> str:
        """Extract conversation ID from URL"""
        url = self.page.url
        # URL format: https://gemini.google.com/app/<conversation_id>
        match = re.search(r"/app/([a-fA-F0-9]+)", url)
        if not match:
            raise LLMInvocationError(f"Could not extract conversation ID from URL: {url}")
        return match.group(1)

    def _extract_user_text(self, container) -> str:
        """
        Extract user's message from container.

        Mirrors content.js lines 989-1011.
        Note: gemini-exporter extracts ALL .user-query-container duplicates,
        but we only need one (the first complete one).
        """
        user_container = container.query_selector(".user-query-container")
        if not user_container:
            raise LLMInvocationError("No user message found in container")

        # Extract text content, excluding UI elements
        text = user_container.inner_text().strip()
        if not text:
            raise LLMInvocationError("User message is empty")

        return text

    def _extract_thinking(self, container) -> Optional[Dict]:
        """
        Extract thinking stages from DOM.

        Mirrors content.js extractThinkingStages() function (lines 807-846).

        Returns:
            Dict with {"stages": [{"stage_name": str, "text": str}, ...]} or None
        """
        thinking_container = container.query_selector('[data-test-id="model-thoughts"]')
        if not thinking_container:
            return None

        stages = []
        elements = thinking_container.query_selector_all("p, div")
        current_stage = None

        for el in elements:
            text = el.inner_text().strip()
            if not text:
                continue

            # Check if element is a stage header (contains bold/strong text)
            bold_el = el.query_selector("strong, b")
            if bold_el and text == bold_el.inner_text().strip():
                # This is a stage header - save previous stage if exists
                if current_stage and current_stage["text"].strip():
                    stages.append(current_stage)

                # Start new stage
                current_stage = {"stage_name": text, "text": ""}
            elif current_stage:
                # This is stage content - add to current stage
                current_stage["text"] += (current_stage["text"] and "\n\n") + text

        # Don't forget the last stage
        if current_stage and current_stage["text"].strip():
            stages.append(current_stage)

        return {"stages": stages} if stages else None

    def _extract_response_text(self, container) -> str:
        """
        Extract response text, excluding thinking blocks.

        Mirrors content.js extractResponseText() function (lines 848-872).
        """
        # Find markdown panel
        markdown_panel = container.query_selector(".markdown-main-panel")
        if not markdown_panel:
            raise LLMInvocationError("No response markdown panel found")

        # Clone to avoid modifying DOM
        clone = markdown_panel.evaluate(
            """
            (element) => {
                const clone = element.cloneNode(true);

                // Remove thinking containers
                clone.querySelectorAll('[data-test-id="model-thoughts"]').forEach(el => el.remove());
                clone.querySelectorAll('button[data-test-id="thoughts-header-button"]').forEach(el => el.remove());

                // Remove other UI elements (but keep code blocks)
                clone.querySelectorAll('button:not(pre button), [role="button"]:not(pre [role="button"])').forEach(el => {
                    if (!el.closest('pre, code')) {
                        el.remove();
                    }
                });

                return clone.innerText;
            }
            """
        )

        response_text = clone.strip()
        if not response_text:
            raise LLMInvocationError("Response text is empty")

        return response_text

    def __del__(self):
        """Cleanup browser resources"""
        if hasattr(self, 'browser') and self.browser:
            self.browser.close()
        if hasattr(self, 'playwright') and self.playwright:
            self.playwright.stop()
