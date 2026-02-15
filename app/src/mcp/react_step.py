# app/src/mcp/react_step.py
"""
Shared helper for specialists using prompt-prix react_step() MCP tool.

Any specialist can become ReAct-capable by:
1. Defining a tool routing table (Dict[str, ToolDef])
2. Defining tool parameter schemas (Dict[str, Dict])
3. Calling call_react_step() in a loop
4. Dispatching pending_tool_calls via dispatch_external_tool()

See text_analysis_specialist.py and project_director.py for examples.
Issue #162 tracks the migration from ReActMixin to this pattern.
"""
import json
import logging
from typing import Dict, Any, List, Optional

from .external_client import sync_call_external_mcp
from .utils import extract_text_from_mcp_result

logger = logging.getLogger(__name__)


class ToolDef:
    """Lightweight tool definition mapping a tool name to an MCP service."""
    __slots__ = ("service", "function", "description", "is_external")

    def __init__(
        self,
        service: str,
        function: str,
        description: str = "",
        is_external: bool = True,
    ):
        self.service = service
        self.function = function
        self.description = description
        self.is_external = is_external


def is_react_available(external_mcp_client) -> bool:
    """Check if prompt-prix MCP is reachable for react_step calls."""
    return (
        external_mcp_client is not None
        and hasattr(external_mcp_client, 'is_connected')
        and external_mcp_client.is_connected("prompt-prix")
    )


def call_react_step(
    external_mcp_client,
    *,
    model_id: str,
    system_prompt: str,
    task_prompt: str,
    trace: List[Dict[str, Any]],
    tool_schemas: List[Dict[str, Any]],
    call_counter: int = 0,
    timeout: float = 600.0,
) -> Dict[str, Any]:
    """
    Call react_step via prompt-prix MCP and parse the result.

    Returns a dict with keys:
    - completed (bool): True if model stopped calling tools
    - final_response (str|None): Text response when completed
    - pending_tool_calls (list): Tool calls to dispatch when not completed
    - call_counter (int): Updated counter for next call
    - thought (str|None): Model reasoning text
    - done_args (dict|None): Raw DONE tool arguments when DONE was normalized

    On error, returns a dict with completed=True and final_response=error message.
    """
    raw_result = sync_call_external_mcp(
        external_mcp_client,
        "prompt-prix",
        "react_step",
        {
            "model_id": model_id,
            "system_prompt": system_prompt,
            "initial_message": task_prompt,
            "trace": trace,
            "mock_tools": None,
            "tools": tool_schemas,
            "call_counter": call_counter,
        },
        timeout=timeout,
    )
    result = parse_react_step_result(raw_result)
    return _normalize_done(result)


def parse_react_step_result(raw_result) -> Any:
    """
    Parse MCP CallToolResult from react_step into a dict.

    Handles three return types from sync_call_external_mcp:
    - dict: Direct return (tests, future bridge changes) — pass through
    - str: Permission denied from PermissionedMcpClient — return as error
    - CallToolResult: MCP SDK type — extract text, parse JSON
    """
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str):
        return {"completed": True, "final_response": f"Error: {raw_result}"}

    text = extract_text_from_mcp_result(raw_result)
    if not text:
        return {"completed": True, "final_response": "Error: react_step returned empty response"}

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"completed": True, "final_response": f"Error: react_step returned {type(parsed).__name__}"}
    except json.JSONDecodeError:
        # Non-JSON text = plain text completion
        return {"completed": True, "final_response": text}


def _normalize_done(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize DONE tool calls so specialists never see them as pending.

    prompt-prix adds DONE to tool schemas and may return it as a pending_tool_call
    instead of setting completed=True. This extracts DONE, marks the result as
    completed, and stores the raw args in done_args for specialist-specific parsing.

    Specialists that need structured DONE data (e.g., EI's is_complete/reasoning)
    read from done_args. Specialists that just need a final message get it from
    final_response (hoisted from done_args if present).
    """
    if result.get("completed"):
        return result

    pending = result.get("pending_tool_calls", [])
    for i, tc in enumerate(pending):
        if tc.get("name") == "DONE":
            args = tc.get("args", {})
            result["completed"] = True
            result["done_args"] = args
            # Hoist final_response for backward compat (PD, TA use this)
            if "final_response" in args:
                result["final_response"] = args["final_response"]
            # Remove DONE from pending (other tool calls in same batch are unlikely but safe)
            result["pending_tool_calls"] = pending[:i] + pending[i+1:]
            logger.info(f"Normalized DONE tool call to completed=True (args: {list(args.keys())})")
            break

    return result


def build_tool_schemas(
    tools: Dict[str, ToolDef],
    params: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert tool definitions to OpenAI function calling format for react_step."""
    schemas = []
    for name, tool_def in tools.items():
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool_def.description,
                "parameters": params.get(name, {"type": "object", "properties": {}}),
            },
        })
    return schemas


def dispatch_external_tool(
    external_mcp_client,
    tool_def: ToolDef,
    tool_args: Dict[str, Any],
) -> str:
    """
    Dispatch a tool call to an external MCP service.

    Returns the text result, or "Error: ..." on failure.
    Specialists can wrap this for enrichment (e.g., PD's filesystem error hints).
    """
    try:
        raw_result = sync_call_external_mcp(
            external_mcp_client,
            tool_def.service,
            tool_def.function,
            tool_args,
        )
        return extract_text_from_mcp_result(raw_result)
    except Exception as e:
        logger.error(f"Tool dispatch failed for {tool_def.function}: {e}")
        return f"Error: {tool_def.function} failed: {e}"
