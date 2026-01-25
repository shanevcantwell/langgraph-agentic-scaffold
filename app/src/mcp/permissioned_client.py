# app/src/mcp/permissioned_client.py
"""
Permissioned MCP Client wrapper for config-driven tool access control.

Wraps ExternalMcpClient to enforce per-specialist tool permissions defined in config.yaml.
Permission errors return helpful messages for LLM self-correction rather than crashing.

See ADR-CORE-051 for architectural details.
"""

import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


class PermissionedMcpClient:
    """
    Wraps ExternalMcpClient with permission checking based on config.yaml.

    Specialists receive a PermissionedMcpClient instead of the raw ExternalMcpClient.
    Unauthorized tool calls return helpful error messages (not exceptions) so the
    LLM can self-correct its plan.

    Example config.yaml:
        specialists:
          batch_processor_specialist:
            tools:
              filesystem:
                - read_file
                - write_file
                - directory_tree

    Example usage:
        # In GraphBuilder.initialize_external_mcp()
        tool_permissions = specialist_config.get("tools", {})
        if tool_permissions:
            specialist.external_mcp_client = PermissionedMcpClient(
                self.external_mcp_client,
                allowed_tools=tool_permissions
            )

    Architecture (ADR-CORE-051):
        Specialist → PermissionedMcpClient → ExternalMcpClient → Container
                           ↓
                   Permission check
                   (config-driven)
    """

    def __init__(
        self,
        inner_client: "ExternalMcpClient",
        allowed_tools: Dict[str, Union[List[str], str]]
    ):
        """
        Initialize permissioned wrapper.

        Args:
            inner_client: The actual ExternalMcpClient
            allowed_tools: Dict mapping service names to allowed tool lists.
                           {"filesystem": ["read_file", "write_file"]}
                           {"filesystem": "*"}  # Wildcard = all tools
        """
        self._inner = inner_client
        self._allowed_tools = allowed_tools
        logger.debug(f"Created PermissionedMcpClient with permissions: {allowed_tools}")

    @property
    def _main_loop(self):
        """Forward _main_loop access to inner client (required by sync_call_external_mcp)."""
        return self._inner._main_loop

    def is_connected(self, service_name: str) -> bool:
        """
        Check if service is connected AND specialist has permission.

        Returns False if:
        - Service not in allowed_tools config
        - Service not actually connected on inner client
        """
        if service_name not in self._allowed_tools:
            logger.debug(f"PermissionedMcpClient: Service '{service_name}' not in allowed tools")
            return False
        return self._inner.is_connected(service_name)

    async def call_tool(
        self,
        service_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Call a tool with permission checking.

        If tool is not permitted, returns a helpful error message string instead
        of raising an exception. This allows the LLM to self-correct its plan.

        Args:
            service_name: Service identifier (e.g., "filesystem")
            tool_name: Tool name (e.g., "read_file")
            arguments: Tool arguments

        Returns:
            Tool result on success, or error message string on permission denial
        """
        # Check if service is permitted at all
        if service_name not in self._allowed_tools:
            error_msg = (
                f"Permission Denied: Service '{service_name}' is not available to this specialist. "
                f"Available services: {list(self._allowed_tools.keys())}. "
                f"Please adjust your plan to use only permitted services."
            )
            logger.warning(f"PermissionedMcpClient: {error_msg}")
            return error_msg

        allowed = self._allowed_tools[service_name]

        # Check wildcard permission
        if allowed == "*":
            return await self._inner.call_tool(service_name, tool_name, arguments)

        # Check explicit tool list
        if tool_name not in allowed:
            error_msg = (
                f"Permission Denied: Tool '{tool_name}' is not permitted on service '{service_name}'. "
                f"Available tools: {list(allowed)}. "
                f"Please adjust your plan to use only permitted tools."
            )
            logger.warning(f"PermissionedMcpClient: {error_msg}")
            return error_msg

        # Permission granted - forward to inner client
        return await self._inner.call_tool(service_name, tool_name, arguments)

    async def list_tools(self, service_name: str) -> List[str]:
        """
        List available tools for a service (filtered by permissions).

        Returns only the tools this specialist is permitted to use.
        """
        if service_name not in self._allowed_tools:
            return []

        allowed = self._allowed_tools[service_name]

        if allowed == "*":
            return await self._inner.list_tools(service_name)

        # Return only permitted tools (intersection with actual available)
        return list(allowed)

    def get_connected_services(self) -> List[str]:
        """
        Get list of services this specialist can access.

        Returns intersection of:
        - Services actually connected on inner client
        - Services permitted in config
        """
        connected = self._inner.get_connected_services()
        permitted = set(self._allowed_tools.keys())
        return [s for s in connected if s in permitted]

    async def health_check(self, service_name: str) -> bool:
        """
        Check if service is healthy (and permitted).
        """
        if service_name not in self._allowed_tools:
            return False
        return await self._inner.health_check(service_name)

    def __repr__(self) -> str:
        services = list(self._allowed_tools.keys())
        return f"PermissionedMcpClient(services={services})"
