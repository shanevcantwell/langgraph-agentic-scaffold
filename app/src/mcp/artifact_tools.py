# app/src/mcp/artifact_tools.py
"""
Shared artifact tools for react_step specialists.

Any specialist running a react_step loop can include artifact tools
by importing from this module. Tools operate on an artifacts snapshot
passed by the caller — no global state, no instance coupling.

read tools: list_artifacts, retrieve_artifact (extracted #195)
write tool:  write_artifact (ADR-076 — data flow primitives)
"""
import json as _json
import random as _random
from typing import Dict, Any

from .react_step import ToolDef


# ---- Name generation for write_artifact ----
# Phase 1: random word-word-word names. Phase 2 (ADR-074): lfm2 batch
# summarizer generates semantically-aligned labels from content.

_ADJECTIVES = [
    "bright", "calm", "cosmic", "crisp", "deft", "eager", "faint", "gentle",
    "hazy", "keen", "lush", "mellow", "nimble", "plush", "quiet", "rapid",
    "serene", "stark", "swift", "terse", "vivid", "warm", "wibbly", "zesty",
]
_NOUNS = [
    "anvil", "bloom", "cedar", "comet", "crystal", "delta", "ember", "falcon",
    "garden", "glider", "heron", "lantern", "marble", "nexus", "opal", "pebble",
    "platypus", "quartz", "reef", "spark", "thistle", "vessel", "willow", "zenith",
]
_SUFFIXES = [
    "blaze", "chime", "drift", "flare", "gleam", "glint", "glitter", "glow",
    "haze", "lilt", "mist", "pulse", "ripple", "shade", "shimmer", "spark",
    "surge", "trace", "trail", "wave", "whirl", "wisp",
]


def _generate_artifact_name(existing_keys: set) -> str:
    """Generate a unique adjective-noun-suffix key not in existing_keys."""
    for _ in range(50):
        name = (
            f"{_random.choice(_ADJECTIVES)}-"
            f"{_random.choice(_NOUNS)}-"
            f"{_random.choice(_SUFFIXES)}"
        )
        if name not in existing_keys:
            return name
    # Fallback: append counter
    return f"artifact-{len(existing_keys)}"


def _resolve_collision(existing_keys: set, requested_key: str) -> str:
    """If requested_key collides, append a numeric suffix."""
    if requested_key not in existing_keys:
        return requested_key
    n = 2
    while f"{requested_key}-{n}" in existing_keys:
        n += 1
    return f"{requested_key}-{n}"


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


def write_artifact(artifacts: dict, content: str, key: str = "") -> str:
    """Persist an observation, decision, or intermediate result as an artifact.

    Mutates the captured artifacts snapshot in place. Immediately visible
    to subsequent list_artifacts / retrieve_artifact calls within the same
    execution. Persists to graph state when the specialist returns.

    Args:
        artifacts: The captured artifacts snapshot (mutated in place).
        content: Content to persist.
        key: Optional requested name. If omitted or collides, a unique name
             is assigned. The actual key is returned in the response.

    Returns:
        Confirmation string with the actual artifact key assigned.
    """
    existing = set(artifacts.keys())
    if key:
        actual_key = _resolve_collision(existing, key)
    else:
        actual_key = _generate_artifact_name(existing)
    artifacts[actual_key] = content
    return f"Artifact written as '{actual_key}' ({len(content)} chars)"


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
    "write_artifact": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Content to persist (observations, decisions, progress)",
            },
            "key": {
                "type": "string",
                "description": "Optional name for the artifact. If omitted or taken, a unique name is assigned.",
            },
        },
        "required": ["content"],
    },
}


def artifact_tool_defs() -> Dict[str, ToolDef]:
    """Standard artifact tools for any react_step specialist."""
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
        "write_artifact": ToolDef(
            service="local",
            function="write_artifact",
            description=(
                "Persist an observation, decision, or intermediate result. "
                "Survives interruption. Optionally suggest a name; the actual "
                "assigned key is returned in the response."
            ),
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
    elif tool_name == "write_artifact":
        return write_artifact(artifacts, tool_args.get("content", ""), tool_args.get("key", ""))
    return f"Error: Unknown artifact tool '{tool_name}'"
