# app/src/specialists/navigator_specialist.py
"""
Navigator Specialist - Tree traversal and complex file operations.

ADR-CORE-027 Phase 2: Provides capabilities beyond FileSpecialist:
- Recursive directory deletion
- Glob pattern search
- Tree navigation with history
- Browser automation (Phase 3)

Uses external navigation-mcp service via ExternalMcpClient.
"""

import json
import logging
from typing import Dict, Any, Optional, List

from langchain_core.messages import AIMessage, HumanMessage

from .base import BaseSpecialist
from ..mcp import sync_call_external_mcp
from ..utils.errors import SpecialistError

logger = logging.getLogger(__name__)


class NavigatorSpecialist(BaseSpecialist):
    """
    Specialist for complex filesystem operations requiring tree traversal.

    Capabilities (beyond FileSpecialist):
    - Recursive delete (directories with contents)
    - Glob pattern search (find files matching patterns)
    - Tree navigation with history (back/forward)

    Architecture:
        User Request → LLM Planning → Navigator Tools → Result

    The specialist:
    1. Uses LLM to understand user intent
    2. Creates a navigator session
    3. Executes filesystem operations
    4. Reports results
    5. Cleans up session
    """

    SERVICE_NAME = "navigator"
    DRIVER_FS = "fs"

    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        self.external_mcp_client = None  # Injected by GraphBuilder
        self._current_session_id: Optional[str] = None

    def _perform_pre_flight_checks(self) -> bool:
        """
        Check if navigator service is available.

        Note: external_mcp_client is injected AFTER specialist loading by GraphBuilder,
        so we can't verify it at load time. Return True to allow loading; runtime
        checks in _execute_logic handle service unavailability gracefully.
        """
        # At load time, external_mcp_client isn't injected yet - allow loading
        if not self.external_mcp_client:
            return True

        # At runtime, check if service is actually connected
        if not self.external_mcp_client.is_connected(self.SERVICE_NAME):
            logger.warning(f"{self.specialist_name}: navigator service not connected")
            return False

        return True

    def _create_session(self) -> Optional[str]:
        """Create a navigator filesystem session."""
        if not self.external_mcp_client:
            return None

        try:
            result = sync_call_external_mcp(
                self.external_mcp_client,
                self.SERVICE_NAME,
                "session_create",
                {
                    "drivers": {
                        self.DRIVER_FS: {
                            "type": "filesystem",
                            "root": "/workspace",
                            "sandbox": True
                        }
                    }
                }
            )
            session_id = self._extract_session_id(result)
            if session_id:
                logger.info(f"Navigator session created: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to create navigator session: {e}")
            return None

    def _destroy_session(self, session_id: str) -> None:
        """Destroy a navigator session."""
        if not self.external_mcp_client or not session_id:
            return

        try:
            sync_call_external_mcp(
                self.external_mcp_client,
                self.SERVICE_NAME,
                "session_destroy",
                {"session_id": session_id}
            )
            logger.info(f"Navigator session destroyed: {session_id}")
        except Exception as e:
            logger.warning(f"Failed to destroy navigator session {session_id}: {e}")

    def _call_navigator(
        self,
        tool_name: str,
        session_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Call a navigator tool with session context.

        Args:
            tool_name: Navigator tool name (e.g., "goto", "list", "delete")
            session_id: Active session ID
            **kwargs: Tool-specific arguments

        Returns:
            Parsed result dict from navigator
        """
        arguments = {
            "session_id": session_id,
            "driver": self.DRIVER_FS,
            **kwargs
        }

        result = sync_call_external_mcp(
            self.external_mcp_client,
            self.SERVICE_NAME,
            tool_name,
            arguments
        )

        return self._parse_result(result)

    def _parse_result(self, result) -> Dict[str, Any]:
        """Parse navigator result into a dict."""
        if result is None:
            return {"error": "No result returned"}

        # Extract text content from MCP result
        text_content = ""
        if hasattr(result, 'content'):
            content = result.content
            if isinstance(content, list) and len(content) > 0:
                text_content = content[0].text if hasattr(content[0], 'text') else str(content[0])
            else:
                text_content = str(content)
        else:
            text_content = str(result)

        # Parse JSON if possible
        try:
            return json.loads(text_content)
        except json.JSONDecodeError:
            return {"content": text_content}

    def _extract_session_id(self, result) -> Optional[str]:
        """Extract session_id from session_create result."""
        parsed = self._parse_result(result)
        return parsed.get("session_id")

    # =========================================================================
    # High-Level Operations
    # =========================================================================

    def delete_recursive(self, session_id: str, path: str) -> Dict[str, Any]:
        """
        Delete a file or directory recursively.

        This is the key capability FileSpecialist lacks.
        """
        result = self._call_navigator(
            "delete",
            session_id,
            target=path,
            recursive=True
        )
        return result

    def find_files(self, session_id: str, pattern: str, path: str = ".") -> Dict[str, Any]:
        """
        Find files matching a glob pattern.

        Args:
            session_id: Active session
            pattern: Glob pattern (e.g., "*.py", "**/*.txt")
            path: Directory to search in (default: current)
        """
        # First navigate to the search directory
        self._call_navigator("goto", session_id, location=path)

        # Execute find with pattern
        result = self._call_navigator(
            "find",
            session_id,
            pattern=pattern
        )
        return result

    def list_directory(self, session_id: str, path: str = ".") -> Dict[str, Any]:
        """List directory contents."""
        self._call_navigator("goto", session_id, location=path)
        return self._call_navigator("list", session_id)

    # =========================================================================
    # Main Execution
    # =========================================================================

    def _execute_logic(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute navigator operations based on user request.

        Uses LLM to interpret the request, then executes appropriate
        navigator operations.
        """
        # Runtime check: external_mcp_client must be injected
        if not self.external_mcp_client:
            return self._handle_navigator_unavailable(state)

        # Check if navigator service is connected
        if not self._perform_pre_flight_checks():
            return self._handle_navigator_unavailable(state)

        # Get user request from messages
        messages = self._get_enriched_messages(state)
        user_request = self._get_last_user_message(messages)

        if not user_request:
            return {
                "messages": [AIMessage(content="No request provided. What file operation would you like me to perform?")]
            }

        # Create session for this operation
        session_id = self._create_session()
        if not session_id:
            return {
                "messages": [AIMessage(
                    content="Unable to connect to navigator service. The complex file operation cannot be completed at this time."
                )]
            }

        try:
            # Use LLM to plan and execute operation
            result = self._execute_with_llm(state, session_id, user_request)
            return result
        finally:
            # Always cleanup session
            self._destroy_session(session_id)

    def _execute_with_llm(
        self,
        state: Dict[str, Any],
        session_id: str,
        user_request: str
    ) -> Dict[str, Any]:
        """
        Use LLM to interpret request and execute navigator operations.

        For Phase 2, we use a simple pattern matching approach.
        Phase 3+ will use full ReActMixin for complex multi-step operations.
        """
        request_lower = user_request.lower()

        # Pattern: Delete directory/folder
        if any(word in request_lower for word in ["delete", "remove", "rm"]):
            if any(word in request_lower for word in ["directory", "folder", "dir"]):
                return self._handle_delete_request(session_id, user_request)

        # Pattern: Find files
        if any(word in request_lower for word in ["find", "search", "locate"]):
            return self._handle_find_request(session_id, user_request)

        # Pattern: List files
        if any(word in request_lower for word in ["list", "ls", "show"]):
            return self._handle_list_request(session_id, user_request)

        # Default: Use LLM to understand and respond
        return self._handle_with_llm(state, session_id, user_request)

    def _handle_delete_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle delete directory requests."""
        # Extract path from request (simple heuristic)
        # TODO: Use LLM for better extraction
        path = self._extract_path_from_request(request)

        if not path:
            return {
                "messages": [AIMessage(
                    content="I couldn't determine which directory to delete. Please specify the path, e.g., 'delete the temp directory'."
                )]
            }

        try:
            # First list to show what will be deleted
            list_result = self.list_directory(session_id, path)

            if "error" in list_result:
                return {
                    "messages": [AIMessage(
                        content=f"Cannot access '{path}': {list_result.get('error', 'Unknown error')}"
                    )]
                }

            items = list_result.get("items", [])

            # Perform recursive delete
            delete_result = self.delete_recursive(session_id, path)

            if "error" in delete_result:
                return {
                    "messages": [AIMessage(
                        content=f"Failed to delete '{path}': {delete_result.get('error', 'Unknown error')}"
                    )]
                }

            # Success response
            return {
                "messages": [AIMessage(
                    content=f"Successfully deleted '{path}' and all its contents ({len(items)} items removed)."
                )],
                "artifacts": {
                    "navigator_operation": {
                        "type": "delete_recursive",
                        "path": path,
                        "items_deleted": len(items),
                        "result": delete_result
                    }
                }
            }

        except Exception as e:
            logger.error(f"Delete operation failed: {e}")
            return {
                "messages": [AIMessage(
                    content=f"Error during delete operation: {str(e)}"
                )]
            }

    def _handle_find_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle find/search file requests."""
        # Extract pattern from request
        pattern = self._extract_pattern_from_request(request)

        if not pattern:
            return {
                "messages": [AIMessage(
                    content="I couldn't determine the search pattern. Please specify, e.g., 'find all .py files' or 'search for *.txt'."
                )]
            }

        try:
            result = self.find_files(session_id, pattern)

            if "error" in result:
                return {
                    "messages": [AIMessage(
                        content=f"Search failed: {result.get('error', 'Unknown error')}"
                    )]
                }

            matches = result.get("matches", result.get("items", []))

            if not matches:
                return {
                    "messages": [AIMessage(
                        content=f"No files found matching pattern '{pattern}'."
                    )]
                }

            # Format results
            match_list = "\n".join(f"- {m}" for m in matches[:20])
            truncation_note = f"\n... and {len(matches) - 20} more" if len(matches) > 20 else ""

            return {
                "messages": [AIMessage(
                    content=f"Found {len(matches)} files matching '{pattern}':\n\n{match_list}{truncation_note}"
                )],
                "artifacts": {
                    "navigator_operation": {
                        "type": "find",
                        "pattern": pattern,
                        "matches": matches,
                        "count": len(matches)
                    }
                }
            }

        except Exception as e:
            logger.error(f"Find operation failed: {e}")
            return {
                "messages": [AIMessage(
                    content=f"Error during search: {str(e)}"
                )]
            }

    def _handle_list_request(self, session_id: str, request: str) -> Dict[str, Any]:
        """Handle list directory requests."""
        path = self._extract_path_from_request(request) or "."

        try:
            result = self.list_directory(session_id, path)

            if "error" in result:
                return {
                    "messages": [AIMessage(
                        content=f"Cannot list '{path}': {result.get('error', 'Unknown error')}"
                    )]
                }

            items = result.get("items", [])

            if not items:
                return {
                    "messages": [AIMessage(content=f"Directory '{path}' is empty.")]
                }

            # Format results
            item_list = "\n".join(f"- {item}" for item in items[:30])
            truncation_note = f"\n... and {len(items) - 30} more" if len(items) > 30 else ""

            return {
                "messages": [AIMessage(
                    content=f"Contents of '{path}' ({len(items)} items):\n\n{item_list}{truncation_note}"
                )],
                "artifacts": {
                    "navigator_operation": {
                        "type": "list",
                        "path": path,
                        "items": items,
                        "count": len(items)
                    }
                }
            }

        except Exception as e:
            logger.error(f"List operation failed: {e}")
            return {
                "messages": [AIMessage(
                    content=f"Error listing directory: {str(e)}"
                )]
            }

    def _handle_with_llm(
        self,
        state: Dict[str, Any],
        session_id: str,
        user_request: str
    ) -> Dict[str, Any]:
        """
        Use LLM to understand and execute complex requests.

        For Phase 2, this is a fallback. Phase 3 will use ReActMixin
        for full agentic control.
        """
        if not self.llm_adapter:
            return {
                "messages": [AIMessage(
                    content="I can help with file operations like:\n"
                            "- Delete a directory: 'delete the temp folder'\n"
                            "- Find files: 'find all .py files'\n"
                            "- List contents: 'list the src directory'\n\n"
                            "What would you like me to do?"
                )]
            }

        # Use LLM to interpret and respond
        from ..llm.adapter import StandardizedLLMRequest

        prompt_content = f"""The user is asking for help with file operations.

User request: {user_request}

I have access to these filesystem operations:
- delete(path, recursive=True): Delete files or directories
- find(pattern): Search for files matching a glob pattern
- list(path): List directory contents

Analyze the request and explain what I should do. If the request is unclear, ask for clarification.
"""

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt_content)],
            tools=None
        )

        response = self.llm_adapter.invoke(request)
        response_text = response.get("text_response", "I'm not sure how to help with that request.")

        return {
            "messages": [AIMessage(content=response_text)]
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_last_user_message(self, messages: List) -> Optional[str]:
        """Extract the last user message content."""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return msg.content
        return None

    def _extract_path_from_request(self, request: str) -> Optional[str]:
        """
        Extract a path from the user request.

        Simple heuristic - looks for quoted strings or common path patterns.
        TODO: Use LLM for better extraction.
        """
        import re

        # Try quoted string first
        quoted = re.search(r'["\']([^"\']+)["\']', request)
        if quoted:
            return quoted.group(1)

        # Try common patterns: "the X directory", "X folder", etc.
        patterns = [
            r'(?:the\s+)?(\S+)\s+(?:directory|folder|dir)',
            r'(?:directory|folder|dir)\s+(\S+)',
            r'(?:in|from|to)\s+(\S+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, request, re.IGNORECASE)
            if match:
                path = match.group(1)
                # Clean up common words
                if path.lower() not in ['the', 'a', 'an', 'this', 'that']:
                    return path

        return None

    def _extract_pattern_from_request(self, request: str) -> Optional[str]:
        """
        Extract a glob pattern from the user request.

        Simple heuristic - looks for file extensions or explicit patterns.
        """
        import re

        # Explicit glob pattern
        glob_match = re.search(r'[\*\?]+[^\s]*', request)
        if glob_match:
            return glob_match.group(0)

        # File extension pattern: ".py files", "*.txt", etc.
        ext_match = re.search(r'\.([a-zA-Z0-9]+)\s+files?', request, re.IGNORECASE)
        if ext_match:
            return f"**/*.{ext_match.group(1)}"

        # "all X files" pattern
        type_match = re.search(r'all\s+(\w+)\s+files?', request, re.IGNORECASE)
        if type_match:
            file_type = type_match.group(1).lower()
            type_to_ext = {
                'python': 'py',
                'javascript': 'js',
                'typescript': 'ts',
                'markdown': 'md',
                'json': 'json',
                'yaml': 'yaml',
                'yml': 'yml',
            }
            ext = type_to_ext.get(file_type, file_type)
            return f"**/*.{ext}"

        return None

    def _handle_navigator_unavailable(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Handle case when navigator service is not available."""
        return {
            "messages": [AIMessage(
                content="The Navigator service is currently unavailable. "
                        "For simple file operations (read, write, delete single files), "
                        "you can use the File Operations specialist instead.\n\n"
                        "Navigator is needed for:\n"
                        "- Recursive directory deletion\n"
                        "- Glob pattern file search\n"
                        "- Tree traversal operations"
            )]
        }

    # =========================================================================
    # MCP Registration (for internal MCP access)
    # =========================================================================

    def register_mcp_services(self, registry):
        """
        Register navigator operations as internal MCP services.

        This allows other specialists to use navigator via mcp_client.call().
        """
        registry.register_service(self.specialist_name, {
            "delete_recursive": self._mcp_delete_recursive,
            "find_files": self._mcp_find_files,
            "list_directory": self._mcp_list_directory,
            "is_available": self._mcp_is_available,
        })
        logger.info(f"Registered 4 MCP services for {self.specialist_name}")

    def _mcp_is_available(self) -> bool:
        """Check if navigator is available (for other specialists)."""
        return self._perform_pre_flight_checks()

    def _mcp_delete_recursive(self, path: str) -> Dict[str, Any]:
        """MCP wrapper for delete_recursive."""
        session_id = self._create_session()
        if not session_id:
            return {"error": "Navigator unavailable"}

        try:
            return self.delete_recursive(session_id, path)
        finally:
            self._destroy_session(session_id)

    def _mcp_find_files(self, pattern: str, path: str = ".") -> Dict[str, Any]:
        """MCP wrapper for find_files."""
        session_id = self._create_session()
        if not session_id:
            return {"error": "Navigator unavailable"}

        try:
            return self.find_files(session_id, pattern, path)
        finally:
            self._destroy_session(session_id)

    def _mcp_list_directory(self, path: str = ".") -> Dict[str, Any]:
        """MCP wrapper for list_directory."""
        session_id = self._create_session()
        if not session_id:
            return {"error": "Navigator unavailable"}

        try:
            return self.list_directory(session_id, path)
        finally:
            self._destroy_session(session_id)
