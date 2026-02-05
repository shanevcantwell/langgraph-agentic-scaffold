#!/usr/bin/env python3
"""
Terminal MCP Server - Sandboxed shell command execution via MCP protocol.

Implements ADR-MCP-005: Terminal Command MCP Service

Security model: Allowlist-based command filtering. Only pre-approved commands
can execute. All execution happens in this container, isolated from LAS.

Usage:
    python terminal_mcp_server.py

Environment variables:
    SECURITY_MODE: "allowlist" (default), "pattern", or "unrestricted"
    WORKSPACE_PATH: Working directory for commands (default: /workspace)
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# Security Configuration
# ============================================================================

# Tier 1: Allowlist (default) - only these base commands are permitted
ALLOWED_COMMANDS = {
    # Navigation & inspection
    "pwd",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "file",
    "stat",
    # Search
    "grep",
    "find",
    # Text processing
    "echo",
    "sort",
    "uniq",
    "tr",
    "cut",
    # File operations (within workspace)
    "mv",
    "mkdir",
    "cp",
    "touch",
    # System info
    "date",
    "whoami",
    "uname",
    "env",
    # Git (read-only)
    "git",
}

# Commands that are always blocked (even in unrestricted mode)
BLOCKED_PATTERNS = [
    "rm -rf",
    "sudo",
    "> /dev",
    "| bash",
    "| sh",
    "curl |",
    "wget |",
    "$(",
    "`",  # Command substitution
]

WORKSPACE_PATH = os.environ.get("WORKSPACE_PATH", "/workspace")
SECURITY_MODE = os.environ.get("SECURITY_MODE", "allowlist")


def is_command_allowed(command: str) -> tuple[bool, str]:
    """
    Check if command is allowed based on security mode.

    Returns: (allowed: bool, reason: str)
    """
    # Always check blocked patterns first
    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return False, f"Blocked pattern detected: '{pattern}'"

    # Extract base command (first word)
    parts = command.strip().split()
    if not parts:
        return False, "Empty command"

    base_command = parts[0]

    if SECURITY_MODE == "unrestricted":
        logger.warning(f"UNRESTRICTED MODE: Allowing command '{command}'")
        return True, "Unrestricted mode"

    if SECURITY_MODE == "allowlist":
        if base_command in ALLOWED_COMMANDS:
            return True, f"Command '{base_command}' is in allowlist"
        return False, f"Command '{base_command}' not in allowlist. Allowed: {sorted(ALLOWED_COMMANDS)}"

    # Default: deny
    return False, "Unknown security mode"


# ============================================================================
# MCP Protocol Implementation (JSON-RPC over stdio)
# ============================================================================

async def handle_initialize(params: dict) -> dict:
    """Handle MCP initialize request."""
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {}
        },
        "serverInfo": {
            "name": "terminal-mcp",
            "version": "1.0.0"
        }
    }


async def handle_tools_list(params: dict) -> dict:
    """Handle tools/list request."""
    return {
        "tools": [
            {
                "name": "run_command",
                "description": "Execute a shell command and return results. Only commands in the allowlist are permitted.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        },
                        "timeout_ms": {
                            "type": "integer",
                            "description": "Maximum execution time in milliseconds (default: 30000)",
                            "default": 30000
                        },
                        "cwd": {
                            "type": "string",
                            "description": f"Working directory (default: {WORKSPACE_PATH})",
                            "default": WORKSPACE_PATH
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "get_cwd",
                "description": "Return the current working directory path",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_allowed_commands",
                "description": "Return the list of allowed commands",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    }


async def handle_tools_call(params: dict) -> dict:
    """Handle tools/call request."""
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name == "run_command":
        return await run_command(
            command=arguments.get("command", ""),
            timeout_ms=arguments.get("timeout_ms", 30000),
            cwd=arguments.get("cwd", WORKSPACE_PATH)
        )
    elif tool_name == "get_cwd":
        return {
            "content": [{"type": "text", "text": WORKSPACE_PATH}]
        }
    elif tool_name == "get_allowed_commands":
        return {
            "content": [{"type": "text", "text": json.dumps(sorted(ALLOWED_COMMANDS))}]
        }
    else:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True
        }


async def run_command(command: str, timeout_ms: int = 30000, cwd: str = WORKSPACE_PATH) -> dict:
    """Execute a shell command with security filtering."""

    # Security check
    allowed, reason = is_command_allowed(command)
    if not allowed:
        logger.warning(f"Command rejected: {command} - {reason}")
        return {
            "content": [{"type": "text", "text": f"Permission denied: {reason}"}],
            "isError": True
        }

    logger.info(f"Executing: {command} (cwd={cwd}, timeout={timeout_ms}ms)")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            cwd=cwd,
            env={**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin"}
        )

        output_parts = []
        if result.stdout:
            output_parts.append(f"stdout:\n{result.stdout}")
        if result.stderr:
            output_parts.append(f"stderr:\n{result.stderr}")
        if not output_parts:
            output_parts.append("(no output)")

        output_parts.append(f"\nexit_code: {result.returncode}")

        return {
            "content": [{"type": "text", "text": "\n".join(output_parts)}]
        }

    except subprocess.TimeoutExpired:
        logger.warning(f"Command timed out: {command}")
        return {
            "content": [{"type": "text", "text": f"Command timed out after {timeout_ms}ms"}],
            "isError": True
        }
    except Exception as e:
        logger.error(f"Command failed: {command} - {e}")
        return {
            "content": [{"type": "text", "text": f"Execution error: {str(e)}"}],
            "isError": True
        }


# ============================================================================
# MCP Server Main Loop
# ============================================================================

async def process_request(request: dict) -> dict:
    """Process a single JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})
    request_id = request.get("id")

    try:
        if method == "initialize":
            result = await handle_initialize(params)
        elif method == "notifications/initialized":
            # Client acknowledgment, no response needed
            return None
        elif method == "tools/list":
            result = await handle_tools_list(params)
        elif method == "tools/call":
            result = await handle_tools_call(params)
        else:
            result = {"error": {"code": -32601, "message": f"Method not found: {method}"}}

        if request_id is not None:
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        return None

    except Exception as e:
        logger.error(f"Error processing request: {e}")
        if request_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)}
            }
        return None


async def main():
    """Main server loop - read JSON-RPC from stdin, write to stdout."""
    logger.info(f"Terminal MCP Server starting (security_mode={SECURITY_MODE}, workspace={WORKSPACE_PATH})")

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            request = json.loads(line.decode().strip())
            response = await process_request(request)

            if response:
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Server error: {e}")
            break

    logger.info("Terminal MCP Server shutting down")


if __name__ == "__main__":
    asyncio.run(main())
