# app/src/mcp/artifact_tools.py
"""
Shared artifact inspection tools for react_step specialists.

Any specialist running a react_step loop can include artifact inspection
by importing from this module. Tools operate on an artifacts snapshot
passed by the caller — no global state, no instance coupling.

Extracted from exit_interview_specialist.py (#195).
"""
import json as _json
from typing import Dict, Any

from .react_step import ToolDef


def list_artifacts(artifacts: dict) -> str:
    """List available artifact keys with type/size hints."""
    if not artifacts:
        return "No artifacts available."
    lines = []
    for key in sorted(artifacts.keys()):
        value = artifacts[key]
        if isinstance(value, dict):
            lines.append(f"  {key}: dict ({len(value)} keys)")
        elif isinstance(value, list):
            lines.append(f"  {key}: list ({len(value)} items)")
        elif isinstance(value, str):
            lines.append(f"  {key}: str ({len(value)} chars)")
        elif isinstance(value, bytes):
            lines.append(f"  {key}: bytes ({len(value)} bytes)")
        else:
            lines.append(f"  {key}: {type(value).__name__}")
    return "Artifacts:\n" + "\n".join(lines)


def retrieve_artifact(artifacts: dict, key: str) -> str:
    """Retrieve a specific artifact's content by key."""
    if key not in artifacts:
        return f"Error: Artifact '{key}' not found. Use list_artifacts to see available keys."
    return format_artifact_value(artifacts[key])


def format_artifact_value(value) -> str:
    """Format an artifact value for display. No truncation (#183)."""
    if value is None:
        return "(empty)"
    if isinstance(value, bytes):
        return f"(binary, {len(value)} bytes)"
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return _json.dumps(value, indent=2, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


# ---- ToolDef + parameter schemas for react_step integration ----

ARTIFACT_TOOL_PARAMS: Dict[str, Dict[str, Any]] = {
    "list_artifacts": {
        "type": "object",
        "properties": {},
    },
    "retrieve_artifact": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Artifact key to retrieve",
            }
        },
        "required": ["key"],
    },
}


def artifact_tool_defs() -> Dict[str, ToolDef]:
    """Standard artifact inspection tools for any react_step specialist."""
    return {
        "list_artifacts": ToolDef(
            service="local",
            function="list_artifacts",
            description="List all artifacts in the workflow state with type hints.",
            is_external=False,
        ),
        "retrieve_artifact": ToolDef(
            service="local",
            function="retrieve_artifact",
            description="Retrieve a specific artifact's content by key.",
            is_external=False,
        ),
    }


def dispatch_artifact_tool(
    tool_name: str, tool_args: dict, artifacts: dict
) -> str:
    """
    Dispatch a local artifact tool call.

    Returns the tool result string, or an error message.
    Intended for use inside a specialist's tool dispatch switch.
    """
    if tool_name == "list_artifacts":
        return list_artifacts(artifacts)
    elif tool_name == "retrieve_artifact":
        return retrieve_artifact(artifacts, tool_args.get("key", ""))
    return f"Error: Unknown artifact tool '{tool_name}'"
