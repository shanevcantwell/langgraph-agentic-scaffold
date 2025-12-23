"""
Navigator Browser Specialist for web navigation with visual grounding.

Uses surf-mcp for web browsing operations including URL navigation,
element clicking via natural language, form filling, and page content extraction.

Note: surf-mcp is browser-only. For filesystem operations, see FileSpecialist.

See ADR-CORE-027 for architectural details.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from ..mcp import sync_call_external_mcp

logger = logging.getLogger(__name__)


class NavigatorBrowserSpecialist(BaseSpecialist):
    """
    Specialist for web navigation with visual grounding.

    Uses surf-mcp to browse websites using natural language descriptions
    for element interaction (Fara visual grounding).

    Architecture (ADR-CORE-027):
        User Request → NavigatorBrowserSpecialist → ExternalMcpClient → surf-mcp
                                                                              ↓
                                                                        Browser Driver
                                                                              ↓
                                                                        Fara (LMStudio)

    Browser operations:
    - goto: Navigate to URL
    - click: Click element by natural language description
    - type: Enter text into form field
    - read: Extract page content
    - snapshot: Capture screenshot
    - act_autonomous: Multi-step autonomous goal completion

    Session-based interaction:
    - Creates browser session with headless Playwright
    - Maintains navigation state across operations
    - Supports storage_state for session persistence
    """

    # Request patterns for operation detection
    NAVIGATE_PATTERNS = [
        r'\b(?:go\s+to|navigate\s+to|open|visit|browse\s+to)\b',
        r'\bhttps?://\S+\b',  # URL detection
    ]
    CLICK_PATTERNS = [
        r'\b(?:click|press|tap|select)\b.*\b(?:button|link|checkbox|radio|element)\b',
        r'\b(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?["\']?[\w\s]+["\']?\b',
    ]
    TYPE_PATTERNS = [
        r'\b(?:type|enter|input|fill)\b.*\b(?:in|into|text)\b',
        r'\b(?:search\s+for|type)\s+["\'][\w\s]+["\']\b',
    ]
    READ_PATTERNS = [
        r'\b(?:read|get|extract|scrape)\b.*\b(?:content|text|page|article)\b',
        r'\bwhat\s+(?:does|is)\s+(?:the|on)\b',
    ]
    SNAPSHOT_PATTERNS = [
        r'\b(?:screenshot|capture|snapshot|take\s+picture)\b',
    ]

    def _perform_pre_flight_checks(self) -> bool:
        """
        Check if navigator browser is available.

        Note: external_mcp_client is injected AFTER specialist loading by GraphBuilder,
        so we can't verify it at load time. Return True to allow loading; runtime
        checks in _execute_logic handle service unavailability gracefully.
        """
        # At load time, external_mcp_client isn't injected yet - allow loading
        if not hasattr(self, 'external_mcp_client') or self.external_mcp_client is None:
            return True

        # At runtime, check if service is actually connected
        if not self.external_mcp_client.is_connected("navigator"):
            logger.warning("NavigatorBrowserSpecialist: Navigator not connected")
            return False

        return True

    def _create_browser_session(self, headless: bool = True) -> Optional[str]:
        """Create a navigator browser session."""
        try:
            result = sync_call_external_mcp(
                self.external_mcp_client,
                "navigator",
                "session_create",
                {
                    "drivers": {
                        "web": {
                            "type": "browser",
                            "headless": headless
                        }
                    }
                }
            )
            return self._extract_session_id(result)
        except Exception as e:
            logger.error(f"Failed to create browser session: {e}")
            return None

    def _destroy_session(self, session_id: str) -> None:
        """Destroy a navigator session."""
        try:
            sync_call_external_mcp(
                self.external_mcp_client,
                "navigator",
                "session_destroy",
                {"session_id": session_id}
            )
        except Exception as e:
            logger.warning(f"Failed to destroy session {session_id}: {e}")

    def _extract_session_id(self, result: Any) -> Optional[str]:
        """Extract session_id from navigator response."""
        try:
            if hasattr(result, 'content') and result.content:
                text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                data = json.loads(text)
                return data.get("session_id")
        except (json.JSONDecodeError, IndexError, AttributeError) as e:
            logger.error(f"Failed to extract session_id: {e}")
        return None

    def _parse_result(self, result: Any) -> Dict[str, Any]:
        """Parse navigator response to dict."""
        if result is None:
            return {"error": "No response from navigator"}

        try:
            if hasattr(result, 'content') and result.content:
                text = result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
                return json.loads(text)
        except (json.JSONDecodeError, IndexError, AttributeError):
            pass

        return {"content": str(result)}

    def _detect_operation(self, request: str) -> str:
        """Detect the type of browser operation from user request."""
        request_lower = request.lower()

        for pattern in self.NAVIGATE_PATTERNS:
            if re.search(pattern, request_lower, re.IGNORECASE):
                return "navigate"

        for pattern in self.CLICK_PATTERNS:
            if re.search(pattern, request_lower, re.IGNORECASE):
                return "click"

        for pattern in self.TYPE_PATTERNS:
            if re.search(pattern, request_lower, re.IGNORECASE):
                return "type"

        for pattern in self.READ_PATTERNS:
            if re.search(pattern, request_lower, re.IGNORECASE):
                return "read"

        for pattern in self.SNAPSHOT_PATTERNS:
            if re.search(pattern, request_lower, re.IGNORECASE):
                return "snapshot"

        return "unknown"

    def _extract_url(self, request: str) -> Optional[str]:
        """Extract URL from user request."""
        url_match = re.search(r'(https?://\S+)', request)
        if url_match:
            return url_match.group(1).rstrip('.,;:!?')
        return None

    def _extract_element_description(self, request: str) -> Optional[str]:
        """Extract element description for click/type operations."""
        # Look for quoted strings first
        quoted = re.search(r'["\']([^"\']+)["\']', request)
        if quoted:
            return quoted.group(1)

        # Look for "the X button/link/etc" patterns
        element_match = re.search(
            r'(?:click|press|tap)\s+(?:on\s+)?(?:the\s+)?([\w\s]+?)\s*(?:button|link|element)?$',
            request, re.IGNORECASE
        )
        if element_match:
            return element_match.group(1).strip()

        return None

    def _extract_text_to_type(self, request: str) -> Optional[str]:
        """Extract text to type from user request."""
        # Look for quoted strings
        quoted = re.search(r'["\']([^"\']+)["\']', request)
        if quoted:
            return quoted.group(1)

        # Look for "type X in/into" patterns
        type_match = re.search(r'type\s+(.+?)\s+(?:in|into)', request, re.IGNORECASE)
        if type_match:
            return type_match.group(1).strip()

        return None

    def _extract_input_description(self, request: str) -> Optional[str]:
        """Extract input field description from user request."""
        # Look for "in/into the X" patterns
        input_match = re.search(r'(?:in|into)\s+(?:the\s+)?([\w\s]+?)(?:\s*$|\s+and)', request, re.IGNORECASE)
        if input_match:
            return input_match.group(1).strip()
        return None

    # =========================================================================
    # Browser Operations
    # =========================================================================

    def navigate_to(self, session_id: str, url: str) -> Dict[str, Any]:
        """Navigate browser to URL."""
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "goto",
            {
                "session_id": session_id,
                "driver": "web",
                "location": url
            }
        )
        return self._parse_result(result)

    def click_element(self, session_id: str, element_description: str) -> Dict[str, Any]:
        """Click element by natural language description (visual grounding)."""
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "click",
            {
                "session_id": session_id,
                "driver": "web",
                "target": element_description
            }
        )
        return self._parse_result(result)

    def type_text(self, session_id: str, text: str, element_description: Optional[str] = None) -> Dict[str, Any]:
        """Type text into element (optionally specified by description)."""
        args = {
            "session_id": session_id,
            "driver": "web",
            "text": text
        }
        if element_description:
            args["target"] = element_description

        result = sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "type",
            args
        )
        return self._parse_result(result)

    def read_content(self, session_id: str) -> Dict[str, Any]:
        """Read current page content."""
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "read",
            {
                "session_id": session_id,
                "driver": "web"
            }
        )
        return self._parse_result(result)

    def take_snapshot(self, session_id: str) -> Dict[str, Any]:
        """Take screenshot of current page."""
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "navigator",
            "snapshot",
            {
                "session_id": session_id,
                "driver": "web"
            }
        )
        return self._parse_result(result)

    # =========================================================================
    # Request Handlers
    # =========================================================================

    def _handle_browser_unavailable(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return graceful message when browser unavailable."""
        return {
            "messages": [AIMessage(content=(
                "Browser navigation is currently unavailable. The navigator service "
                "may not be running or browser support may not be configured.\n\n"
                "To enable browser navigation:\n"
                "1. Start the navigator container: `docker-compose --profile navigator up -d`\n"
                "2. Ensure Playwright is installed in the container\n"
                "3. For visual grounding, load the Fara model in LMStudio"
            ))]
        }

    def _handle_navigate_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle URL navigation request."""
        url = self._extract_url(request)
        if not url:
            return {
                "messages": [AIMessage(content=(
                    "I couldn't find a URL in your request. Please specify the URL "
                    "you'd like to navigate to, for example:\n"
                    "- 'Go to https://example.com'\n"
                    "- 'Navigate to https://google.com'"
                ))]
            }

        result = self.navigate_to(session_id, url)

        if "error" in result:
            return {
                "messages": [AIMessage(content=f"Failed to navigate to {url}: {result['error']}")]
            }

        return {
            "messages": [AIMessage(content=f"Navigated to {url}.")],
            "artifacts": {"browser_operation": {"type": "navigate", "url": url, "result": result}}
        }

    def _handle_click_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle click element request."""
        element = self._extract_element_description(request)
        if not element:
            return {
                "messages": [AIMessage(content=(
                    "I couldn't determine which element to click. Please describe "
                    "the element naturally, for example:\n"
                    "- 'Click the Submit button'\n"
                    "- 'Click the \"Login\" link'"
                ))]
            }

        result = self.click_element(session_id, element)

        if "error" in result:
            return {
                "messages": [AIMessage(content=f"Failed to click '{element}': {result['error']}")]
            }

        return {
            "messages": [AIMessage(content=f"Clicked '{element}'.")],
            "artifacts": {"browser_operation": {"type": "click", "element": element, "result": result}}
        }

    def _handle_type_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle type text request."""
        text = self._extract_text_to_type(request)
        if not text:
            return {
                "messages": [AIMessage(content=(
                    "I couldn't determine what text to type. Please specify the text "
                    "in quotes, for example:\n"
                    "- 'Type \"hello world\" in the search box'\n"
                    "- 'Enter \"my query\" into the input field'"
                ))]
            }

        element = self._extract_input_description(request)
        result = self.type_text(session_id, text, element)

        if "error" in result:
            target = f" into '{element}'" if element else ""
            return {
                "messages": [AIMessage(content=f"Failed to type '{text}'{target}: {result['error']}")]
            }

        target_msg = f" into '{element}'" if element else ""
        return {
            "messages": [AIMessage(content=f"Typed '{text}'{target_msg}.")],
            "artifacts": {"browser_operation": {"type": "type", "text": text, "element": element, "result": result}}
        }

    def _handle_read_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle read page content request."""
        result = self.read_content(session_id)

        if "error" in result:
            return {
                "messages": [AIMessage(content=f"Failed to read page content: {result['error']}")]
            }

        content = result.get("content", result.get("text", str(result)))
        # Truncate long content
        if len(content) > 2000:
            content = content[:2000] + "\n\n... (content truncated)"

        return {
            "messages": [AIMessage(content=f"Page content:\n\n{content}")],
            "artifacts": {"browser_operation": {"type": "read", "result": result}}
        }

    def _handle_snapshot_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle screenshot request."""
        result = self.take_snapshot(session_id)

        if "error" in result:
            return {
                "messages": [AIMessage(content=f"Failed to take screenshot: {result['error']}")]
            }

        return {
            "messages": [AIMessage(content="Screenshot captured.")],
            "artifacts": {"browser_operation": {"type": "snapshot", "result": result}}
        }

    def _handle_unknown_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle unrecognized browser request."""
        return {
            "messages": [AIMessage(content=(
                "I'm not sure what browser operation you'd like to perform. "
                "I can help with:\n\n"
                "- **Navigate**: 'Go to https://example.com'\n"
                "- **Click**: 'Click the Submit button'\n"
                "- **Type**: 'Type \"hello\" in the search box'\n"
                "- **Read**: 'Read the page content'\n"
                "- **Screenshot**: 'Take a screenshot'\n\n"
                "Please try rephrasing your request."
            ))]
        }

    # =========================================================================
    # Session Persistence (ADR-CORE-027 Phase 4)
    # =========================================================================

    # Artifact key for storing persistent session info
    BROWSER_SESSION_ARTIFACT_KEY = "browser_session"

    def _get_existing_session(self, state: Dict[str, Any]) -> Optional[str]:
        """Get existing session_id from state artifacts if available."""
        artifacts = state.get("artifacts", {})
        session_info = artifacts.get(self.BROWSER_SESSION_ARTIFACT_KEY, {})
        return session_info.get("session_id")

    def _validate_session(self, session_id: str) -> bool:
        """Check if an existing session is still valid."""
        try:
            # Try to read current page to validate session
            result = sync_call_external_mcp(
                self.external_mcp_client,
                "navigator",
                "current",
                {
                    "session_id": session_id,
                    "driver": "web"
                }
            )
            # If we get here without error, session is valid
            parsed = self._parse_result(result)
            return "error" not in parsed
        except Exception as e:
            logger.warning(f"Session {session_id} validation failed: {e}")
            return False

    def _get_or_create_session(self, state: Dict[str, Any], persist: bool = True) -> Optional[str]:
        """Get existing valid session or create a new one.

        Args:
            state: Graph state containing artifacts
            persist: If True, enables session persistence (default True)

        Returns:
            Valid session_id or None if creation failed
        """
        if persist:
            # Try to reuse existing session
            existing_session = self._get_existing_session(state)
            if existing_session:
                if self._validate_session(existing_session):
                    logger.info(f"Reusing existing browser session: {existing_session}")
                    return existing_session
                else:
                    logger.info(f"Existing session {existing_session} invalid, creating new one")

        # Create new session
        return self._create_browser_session()

    def _create_session_artifact(self, session_id: str) -> Dict[str, Any]:
        """Create artifact dict for session persistence."""
        return {
            self.BROWSER_SESSION_ARTIFACT_KEY: {
                "session_id": session_id,
                "persist": True
            }
        }

    def _merge_result_with_session(
        self,
        result: Dict[str, Any],
        session_id: str,
        persist: bool = True
    ) -> Dict[str, Any]:
        """Merge operation result with session persistence artifact."""
        if not persist:
            return result

        # Get existing artifacts from result
        artifacts = result.get("artifacts", {})

        # Add session info
        artifacts[self.BROWSER_SESSION_ARTIFACT_KEY] = {
            "session_id": session_id,
            "persist": True
        }

        result["artifacts"] = artifacts
        return result

    # =========================================================================
    # Main Execution
    # =========================================================================

    def _execute_logic(self, state: Dict[str, Any], persist_session: bool = True) -> Dict[str, Any]:
        """Execute browser operation based on user request.

        Args:
            state: Graph state with messages and artifacts
            persist_session: If True, session is persisted for multi-turn conversations
                           If False, session is destroyed after operation (default True)

        Session Persistence (ADR-CORE-027 Phase 4):
        When persist_session=True:
        - Checks artifacts for existing session_id
        - Validates existing session is still alive
        - Creates new session if needed
        - Stores session_id in returned artifacts
        - Session remains alive for subsequent invocations

        To end a persistent session, either:
        - Call cleanup_session() explicitly
        - Let session timeout naturally (default 1 hour)
        - Start with persist_session=False
        """
        # Runtime check: external_mcp_client must be injected
        if not hasattr(self, 'external_mcp_client') or not self.external_mcp_client:
            return self._handle_browser_unavailable(state)

        # Check if navigator service is connected
        if not self._perform_pre_flight_checks():
            return self._handle_browser_unavailable(state)

        # Extract user request
        messages = state.get("messages", [])
        request = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                request = msg.content
                break

        if not request:
            return {
                "messages": [AIMessage(content="No browser request provided.")]
            }

        # Get or create session
        session_id = self._get_or_create_session(state, persist=persist_session)
        if not session_id:
            return {
                "messages": [AIMessage(content=(
                    "Failed to create browser session. The browser driver may not be "
                    "available or Playwright may not be installed."
                ))]
            }

        try:
            # Detect operation type
            operation = self._detect_operation(request)

            # Route to handler
            if operation == "navigate":
                result = self._handle_navigate_request(session_id, request)
            elif operation == "click":
                result = self._handle_click_request(session_id, request)
            elif operation == "type":
                result = self._handle_type_request(session_id, request)
            elif operation == "read":
                result = self._handle_read_request(session_id, request)
            elif operation == "snapshot":
                result = self._handle_snapshot_request(session_id, request)
            else:
                result = self._handle_unknown_request(session_id, request)

            # Merge session persistence into result
            return self._merge_result_with_session(result, session_id, persist=persist_session)

        except Exception as e:
            logger.error(f"Browser operation failed: {e}")
            if not persist_session:
                self._destroy_session(session_id)
            return {
                "messages": [AIMessage(content=f"Browser operation failed: {e}")]
            }

        finally:
            # Only cleanup if not persisting
            if not persist_session:
                self._destroy_session(session_id)

    def cleanup_session(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Explicitly cleanup a persistent browser session.

        Call this when a conversation ends or when you want to
        start fresh in subsequent invocations.

        Args:
            state: Graph state containing session artifact

        Returns:
            State update clearing the session artifact
        """
        session_id = self._get_existing_session(state)
        if session_id:
            self._destroy_session(session_id)
            logger.info(f"Cleaned up persistent browser session: {session_id}")

        return {
            "artifacts": {
                self.BROWSER_SESSION_ARTIFACT_KEY: None
            },
            "messages": [AIMessage(content="Browser session ended.")]
        }

    # =========================================================================
    # MCP Service Interface
    # =========================================================================

    def register_mcp_services(self, registry) -> None:
        """Register MCP services for other specialists to use."""
        registry.register_service(
            self.specialist_name,
            {
                "navigate_to": self._mcp_navigate_to,
                "click_element": self._mcp_click_element,
                "type_text": self._mcp_type_text,
                "read_content": self._mcp_read_content,
                "take_snapshot": self._mcp_take_snapshot,
                "is_available": self._mcp_is_available,
            }
        )

    def _mcp_is_available(self) -> bool:
        """Check if browser navigation is available."""
        return self._perform_pre_flight_checks()

    def _mcp_navigate_to(self, url: str) -> Dict[str, Any]:
        """MCP service: Navigate to URL."""
        session_id = self._create_browser_session()
        if not session_id:
            return {"error": "Failed to create browser session"}
        try:
            return self.navigate_to(session_id, url)
        finally:
            self._destroy_session(session_id)

    def _mcp_click_element(self, element_description: str) -> Dict[str, Any]:
        """MCP service: Click element."""
        session_id = self._create_browser_session()
        if not session_id:
            return {"error": "Failed to create browser session"}
        try:
            return self.click_element(session_id, element_description)
        finally:
            self._destroy_session(session_id)

    def _mcp_type_text(self, text: str, element_description: Optional[str] = None) -> Dict[str, Any]:
        """MCP service: Type text."""
        session_id = self._create_browser_session()
        if not session_id:
            return {"error": "Failed to create browser session"}
        try:
            return self.type_text(session_id, text, element_description)
        finally:
            self._destroy_session(session_id)

    def _mcp_read_content(self) -> Dict[str, Any]:
        """MCP service: Read page content."""
        session_id = self._create_browser_session()
        if not session_id:
            return {"error": "Failed to create browser session"}
        try:
            return self.read_content(session_id)
        finally:
            self._destroy_session(session_id)

    def _mcp_take_snapshot(self) -> Dict[str, Any]:
        """MCP service: Take screenshot."""
        session_id = self._create_browser_session()
        if not session_id:
            return {"error": "Failed to create browser session"}
        try:
            return self.take_snapshot(session_id)
        finally:
            self._destroy_session(session_id)
