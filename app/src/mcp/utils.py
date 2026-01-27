# app/src/mcp/utils.py
"""MCP utility functions."""
from typing import Any


def extract_text_from_mcp_result(result: Any) -> str:
    """
    Extract text content from external MCP result object.

    MCP results typically have structure:
        result.content = [TextContent(text="..."), ...]

    This handles None, empty, and various response shapes.

    Args:
        result: MCP CallToolResult or similar object

    Returns:
        Extracted text string, or empty string if no text content
    """
    if result is None:
        return ""

    if hasattr(result, 'content'):
        content = result.content
        if isinstance(content, list) and len(content) > 0:
            first = content[0]
            if hasattr(first, 'text'):
                # Ensure text is always a string (MCP may have parsed JSON into dicts)
                text = first.text
                return text if isinstance(text, str) else str(text)
            return str(first)
        return str(content)

    return str(result)
