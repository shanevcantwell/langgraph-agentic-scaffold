"""
External MCP Client for containerized MCP servers.

This module provides async communication with external MCP servers (Node.js,
Docker containers, etc.) using the official MCP Python SDK and JSON-RPC protocol.

Architecture:
- Separate from internal McpClient (Python function calls)
- Async subprocess management via stdio transport
- Long-lived container connections (launched at startup)
- Fail-fast error handling (Stage 1 - no fallback)

See ADR-MCP-003 for architectural details.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    # Graceful handling if mcp package not installed
    ClientSession = None  # type: ignore
    StdioServerParameters = None  # type: ignore
    stdio_client = None  # type: ignore

logger = logging.getLogger(__name__)


class ExternalMcpClient:
    """
    Client for external MCP containers (Node.js servers, Docker, etc).

    Manages subprocess lifecycle and JSON-RPC protocol communication using
    the official MCP Python SDK. Separate from internal McpClient (Python
    function calls).

    Example Usage:
        ```python
        # Initialization at startup
        client = ExternalMcpClient(config)
        await client.connect_service(
            service_name="filesystem",
            command="docker",
            args=["run", "-i", "--rm", "-v", "/workspace:/projects", "mcp/filesystem", "/projects"]
        )

        # Tool invocation
        result = await client.call_tool(
            service_name="filesystem",
            tool_name="read_file",
            arguments={"path": "/projects/data.txt"}
        )

        # Cleanup at shutdown
        await client.cleanup()
        ```

    Architecture Pattern (ADR-MCP-003):
        Specialist → ExternalMcpClient → Container Pool → External MCP Server
                                              ↓
                                        JSON-RPC via stdio
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize external MCP client.

        Args:
            config: Full application config dict (expects config["mcp"]["external_mcp"])

        Raises:
            ImportError: If mcp package not installed
        """
        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP Python SDK not installed. Install with: pip install mcp\n"
                "See ADR-MCP-003 for setup instructions."
            )

        self.config = config.get("mcp", {}).get("external_mcp", {})
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.tracing_enabled = self.config.get("tracing_enabled", True)
        logger.info("Initialized ExternalMcpClient")

    async def connect_service(
        self,
        service_name: str,
        command: str,
        args: List[str],
        env: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """
        Connect to an external MCP server via subprocess.

        Launches subprocess (typically Docker container) and establishes
        JSON-RPC session using stdio transport.

        Args:
            service_name: Identifier for the service (e.g., "filesystem")
            command: Executable command (e.g., "docker")
            args: Command arguments (e.g., ["run", "-i", "--rm", "mcp/filesystem"])
            env: Optional environment variables for subprocess

        Returns:
            List of tool names available on the service

        Raises:
            RuntimeError: If connection fails
            ValueError: If service already connected
        """
        if service_name in self.sessions:
            raise ValueError(
                f"External MCP service '{service_name}' already connected. "
                "Call cleanup() before reconnecting."
            )

        logger.info(f"Connecting to external MCP service '{service_name}'...")
        logger.debug(f"Command: {command} {' '.join(args)}")

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env
        )

        try:
            # Launch subprocess and get stdio streams
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            read, write = stdio_transport

            # Create session
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )

            # Initialize connection (handshake)
            await session.initialize()

            # Store session
            self.sessions[service_name] = session

            # List available tools for logging
            response = await session.list_tools()
            tools = [tool.name for tool in response.tools]
            logger.info(
                f"✓ Connected to external MCP service '{service_name}' "
                f"with {len(tools)} tools: {tools}"
            )

            return tools

        except Exception as e:
            logger.error(
                f"Failed to connect to external MCP service '{service_name}': {e}",
                exc_info=True
            )
            raise RuntimeError(
                f"External MCP service '{service_name}' connection failed: {e}\n"
                f"Command: {command} {' '.join(args)}\n"
                "Check that:\n"
                "  1. Docker is running (if using docker command)\n"
                "  2. Container image is built/pulled\n"
                "  3. Volume mounts are correct\n"
                "  4. Command arguments are valid"
            ) from e

    async def call_tool(
        self,
        service_name: str,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Call a tool on an external MCP service.

        Fail-fast error handling (Stage 1 - no retry/fallback).

        Args:
            service_name: Service identifier (e.g., "filesystem")
            tool_name: Tool name (e.g., "read_file")
            arguments: Tool arguments (e.g., {"path": "/workspace/data.txt"})

        Returns:
            Tool result (structure depends on tool)

        Raises:
            ValueError: If service not connected
            RuntimeError: If tool call fails
        """
        if service_name not in self.sessions:
            available_services = list(self.sessions.keys())
            raise ValueError(
                f"External MCP service '{service_name}' not connected. "
                f"Available services: {available_services or 'none'}\n"
                "Call connect_service() first."
            )

        session = self.sessions[service_name]
        arguments = arguments or {}

        logger.debug(
            f"Calling external MCP tool: {service_name}.{tool_name}({arguments})"
        )

        try:
            result = await session.call_tool(tool_name, arguments=arguments)

            if self.tracing_enabled:
                logger.debug(
                    f"✓ External MCP call succeeded: {service_name}.{tool_name}()"
                )

            return result

        except Exception as e:
            logger.error(
                f"External MCP call failed: {service_name}.{tool_name}({arguments}) - {e}",
                exc_info=True
            )
            raise RuntimeError(
                f"External MCP tool call failed: {service_name}.{tool_name}()\n"
                f"Error: {e}\n"
                "This is a fail-fast error (no fallback in Stage 1)."
            ) from e

    async def list_tools(self, service_name: str) -> List[str]:
        """
        List available tools for a connected service.

        Args:
            service_name: Service identifier

        Returns:
            List of tool names

        Raises:
            ValueError: If service not connected
        """
        if service_name not in self.sessions:
            raise ValueError(
                f"External MCP service '{service_name}' not connected"
            )

        session = self.sessions[service_name]
        response = await session.list_tools()
        return [tool.name for tool in response.tools]

    async def health_check(self, service_name: str) -> bool:
        """
        Check if external MCP service is still alive.

        Uses list_tools() as a ping operation.

        Args:
            service_name: Service identifier

        Returns:
            True if service responsive, False otherwise
        """
        try:
            await self.list_tools(service_name)
            return True
        except Exception as e:
            logger.warning(f"Health check failed for '{service_name}': {e}")
            return False

    async def cleanup(self):
        """
        Close all connections and cleanup resources.

        Closes stdio streams and terminates container subprocesses.
        Should be called at application shutdown.
        """
        logger.info("Cleaning up external MCP connections...")
        try:
            await self.exit_stack.aclose()
            service_names = list(self.sessions.keys())
            self.sessions.clear()
            logger.info(f"✓ Closed {len(service_names)} external MCP connections: {service_names}")
        except Exception as e:
            logger.error(f"Error during external MCP cleanup: {e}", exc_info=True)

    def is_connected(self, service_name: str) -> bool:
        """
        Check if service is connected (session exists).

        Args:
            service_name: Service identifier

        Returns:
            True if connected, False otherwise
        """
        return service_name in self.sessions

    def get_connected_services(self) -> List[str]:
        """
        Get list of currently connected service names.

        Returns:
            List of service names
        """
        return list(self.sessions.keys())


def sync_call_external_mcp(
    external_client: ExternalMcpClient,
    service_name: str,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None
) -> Any:
    """
    Bridge sync specialist code to async external MCP.

    Temporary workaround for calling async external MCP from sync specialists.
    Creates new event loop for each call (overhead, but functional).

    See ADR-CORE-014 for long-term async migration plan.

    Args:
        external_client: ExternalMcpClient instance
        service_name: Service identifier (e.g., "filesystem")
        tool_name: Tool name (e.g., "read_file")
        arguments: Tool arguments

    Returns:
        Tool result

    Raises:
        RuntimeError: If tool call fails

    Example:
        ```python
        # In sync specialist code
        result = sync_call_external_mcp(
            self.external_mcp_client,
            "filesystem",
            "read_file",
            {"path": "/projects/data.txt"}
        )
        ```

    Note:
        This function should be replaced when graph execution migrates to async
        (ADR-CORE-014). It's a temporary bridge to enable external MCP usage
        without full async migration.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            external_client.call_tool(service_name, tool_name, arguments)
        )
    finally:
        loop.close()
