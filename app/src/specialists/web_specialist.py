import asyncio
import logging
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from pydantic import ValidationError

from .base import BaseSpecialist
from ..strategies.search.base import BaseSearchStrategy, SearchRequest

if TYPE_CHECKING:
    from ..mcp.services.visual_browser_service import VisualBrowserService

logger = logging.getLogger(__name__)

class WebSpecialist(BaseSpecialist):
    """
    The execution primitive of the Deep Research architecture.
    A pure worker that executes web-related tasks (Search, Browse).
    It has NO internal LLM loop and NO knowledge of SystemPlans.
    It expects a 'web_task' in the scratchpad.

    Capabilities:
        - search: Web search via injected search strategy (DuckDuckGo, Brave, etc.)
        - browse: Visual browsing via Fara+Playwright (locate elements by description)

    Visual Browse Example:
        web_task = {
            "capability": "browse",
            "params": {
                "url": "https://example.com",
                "actions": [
                    {"action": "click", "description": "The login button"},
                    {"action": "type", "description": "Email input", "text": "user@example.com"},
                    {"action": "verify", "description": "Success message"}
                ]
            }
        }
    """

    def __init__(
        self,
        specialist_name: str,
        specialist_config: Dict[str, Any],
        search_strategy: Optional[BaseSearchStrategy] = None,
        visual_browser: Optional["VisualBrowserService"] = None
    ):
        super().__init__(specialist_name, specialist_config)
        self.search_strategy = search_strategy
        self.visual_browser = visual_browser

        if self.search_strategy:
            logger.info(f"WebSpecialist initialized with search strategy: {self.search_strategy.__class__.__name__}")
        else:
            logger.warning("WebSpecialist initialized WITHOUT a search strategy. Search will fail.")

        if self.visual_browser:
            logger.info("WebSpecialist initialized with visual browser (Fara+Playwright)")
        else:
            logger.info("WebSpecialist initialized WITHOUT visual browser. Visual browse will fall back to static.")

    def register_mcp_services(self, registry):
        """Expose search and visual browse capabilities via MCP."""
        services = {
            "search": self._perform_search,
        }

        # Add visual browser functions if available
        if self.visual_browser:
            services.update({
                "visual_navigate": self._visual_navigate,
                "visual_click": self._visual_click,
                "visual_type": self._visual_type,
                "visual_verify": self._visual_verify,
                "visual_screenshot": self._visual_screenshot,
            })

        registry.register_service(self.specialist_name, services)

    def _perform_search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Executes a web search using the injected strategy.
        """
        if not self.search_strategy:
            error_msg = "No search strategy configured for WebSpecialist."
            logger.error(error_msg)
            return [{"title": "Configuration Error", "url": "", "snippet": error_msg}]

        request = SearchRequest(query=query, max_results=max_results)
        return self.search_strategy.execute(request)


    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Executes a web task defined in the scratchpad.
        Expected format: state['scratchpad']['web_task'] = {'capability': 'search', 'params': {'query': '...'}}
        """
        scratchpad = state.get("scratchpad", {})
        task = scratchpad.get("web_task")
        
        if not task:
            logger.warning("WebSpecialist executed but no 'web_task' found in scratchpad.")
            return {"error": "No web_task found in scratchpad."}

        try:
            capability = task.get("capability")
            params = task.get("params", {})
            
            logger.info(f"WebSpecialist executing capability: {capability}")
            
            if capability == "search":
                query = params.get("query")
                if not query:
                    return {"error": "Missing 'query' parameter for search."}
                
                # Execute Search Strategy
                results = self._perform_search(query)
                return {"search_results": results}
            
            elif capability == "browse":
                url = params.get("url")
                actions = params.get("actions", [])

                if not url:
                    return {"error": "Missing 'url' parameter for browse."}

                # Use visual browser if available, otherwise fall back to static browse
                if self.visual_browser:
                    return self._execute_visual_browse(url, actions)
                else:
                    return self._execute_static_browse(url)
            
            else:
                return {"error": f"Unknown capability: {capability}"}

        except Exception as e:
            logger.error(f"Unexpected error in WebSpecialist: {e}", exc_info=True)
            raise # Let NodeExecutor catch it

    # =========================================================================
    # Visual Browser Methods (Fara+Playwright)
    # =========================================================================

    def _execute_visual_browse(self, url: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute visual browsing session with Fara+Playwright.

        Args:
            url: URL to navigate to
            actions: List of actions to perform, each with:
                - action: "click", "type", or "verify"
                - description: Natural language element description
                - text: (for type action) Text to type

        Returns:
            Dict with results of each action and final screenshot
        """
        logger.info(f"WebSpecialist: Starting visual browse to {url}")

        # Run async browse in sync context
        return asyncio.run(self._async_visual_browse(url, actions))

    async def _async_visual_browse(self, url: str, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Async implementation of visual browse."""
        results = []

        try:
            # Launch browser and navigate
            await self.visual_browser.launch()
            nav_result = await self.visual_browser.navigate(url)

            if not nav_result.get("success"):
                return {"error": f"Navigation failed: {nav_result.get('error')}", "url": url}

            results.append({"action": "navigate", "url": url, "result": nav_result})

            # Execute each action
            for action_spec in actions:
                action = action_spec.get("action")
                description = action_spec.get("description", "")

                if action == "click":
                    result = await self.visual_browser.visual_click(description)
                elif action == "type":
                    text = action_spec.get("text", "")
                    result = await self.visual_browser.visual_type(description, text)
                elif action == "verify":
                    result = await self.visual_browser.visual_verify(description)
                else:
                    result = {"error": f"Unknown action: {action}"}

                results.append({"action": action, "description": description, "result": result})

                # Stop on failure if not verify
                if action != "verify" and not result.get("success", result.get("exists", False)):
                    logger.warning(f"Visual browse action failed: {action} - {description}")
                    break

            # Capture final screenshot
            final_screenshot = await self.visual_browser.screenshot()

            return {
                "url": url,
                "actions_executed": len(results),
                "results": results,
                "final_screenshot": final_screenshot,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Visual browse failed: {e}", exc_info=True)
            return {"error": str(e), "url": url, "status": "error"}

        finally:
            await self.visual_browser.close()

    def _execute_static_browse(self, url: str) -> Dict[str, Any]:
        """
        Fallback static browse using requests+BeautifulSoup.
        Used when visual browser is not available.
        """
        import requests
        from bs4 import BeautifulSoup

        logger.info(f"WebSpecialist: Static browse to {url}")

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove script and style
            for script in soup(["script", "style"]):
                script.decompose()

            text = soup.get_text(separator='\n')
            lines = (line.strip() for line in text.splitlines())
            text = '\n'.join(chunk for chunk in lines if chunk)

            return {
                "url": url,
                "title": soup.title.string if soup.title else "No Title",
                "content": text[:10000],  # Truncate for sanity
                "status": "success",
                "mode": "static"
            }

        except Exception as e:
            logger.error(f"Static browse failed: {e}")
            return {"url": url, "error": str(e), "status": "error"}

    # =========================================================================
    # MCP Service Wrappers for Visual Browser
    # =========================================================================

    def _visual_navigate(self, url: str) -> Dict[str, Any]:
        """MCP wrapper: Navigate to URL."""
        if not self.visual_browser:
            return {"error": "Visual browser not configured"}
        return asyncio.run(self.visual_browser.navigate(url))

    def _visual_click(self, description: str) -> Dict[str, Any]:
        """MCP wrapper: Click element by description."""
        if not self.visual_browser:
            return {"error": "Visual browser not configured"}
        return asyncio.run(self.visual_browser.visual_click(description))

    def _visual_type(self, description: str, text: str) -> Dict[str, Any]:
        """MCP wrapper: Type into element by description."""
        if not self.visual_browser:
            return {"error": "Visual browser not configured"}
        return asyncio.run(self.visual_browser.visual_type(description, text))

    def _visual_verify(self, description: str) -> Dict[str, Any]:
        """MCP wrapper: Verify element exists by description."""
        if not self.visual_browser:
            return {"error": "Visual browser not configured"}
        return asyncio.run(self.visual_browser.visual_verify(description))

    def _visual_screenshot(self) -> str:
        """MCP wrapper: Capture screenshot."""
        if not self.visual_browser:
            return ""
        return asyncio.run(self.visual_browser.screenshot())
