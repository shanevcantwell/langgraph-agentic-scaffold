# app/src/utils/state_pruner.py
import json
import os
from typing import Dict, Any

from ..specialists.schemas._archiver import SuccessReport
from ..graph.state import GraphState
from ..utils.report_schema import ErrorReport


def prune_state(state: GraphState) -> Dict[str, Any]:
    """
    Takes a GraphState object and returns a pruned, human-readable dictionary
    suitable for inclusion in an error report.
    """
    pruned = {}

    # Prune messages to a summary of the last 3
    if messages := state.get("messages"):
        pruned["messages_summary"] = [
            f"{msg.type}: {msg.content[:100]}..." for msg in messages[-3:]
        ]

    # Include key metadata
    for key in ["turn_count", "next_specialist", "task_is_complete", "routing_history", "scratchpad", "artifacts"]:
        if value := state.get(key):
            pruned[key] = value

    # --- Deprecated Fields ---

    # Include smaller, valuable artifacts as-is
    for key in ["system_plan", "critique_artifact", "extracted_data", "json_artifact"]:
        if value := state.get(key):
            pruned[key] = value

    # Include key metadata
    return pruned

def generate_report(report_data: ErrorReport) -> str:
    """
    Takes an ErrorReport Pydantic model and formats it into a shareable
    Markdown string.
    """
    report_parts = [
        f"# 🚨 Agentic Workflow Error Report",
        f"- **Timestamp (UTC):** {report_data.timestamp.isoformat()}",
        f"- **Error:** `{report_data.error_message}`",
        "---",
        f"## 🛤️ Routing History\n`{' -> '.join(report_data.routing_history) if report_data.routing_history else 'N/A'}`",
        "---",
        f"## 📦 Pruned State at Time of Error\n```json\n{json.dumps(report_data.pruned_state, indent=2)}\n```",
        "---",
        f"## 📄 Traceback\n```\n{report_data.traceback}\n```"
    ]
    return "\n\n".join(report_parts)

def _format_trace(trace: list, trace_name: str) -> str:
    """Format a resume_trace (or legacy research_trace_N) as a readable tool call log."""
    if not trace or not isinstance(trace, list):
        return f"```\n{trace}\n```"

    lines = [f"**{len(trace)} tool calls:**\n"]
    for i, entry in enumerate(trace):
        if not isinstance(entry, dict):
            lines.append(f"{i+1}. `{entry}`")
            continue

        iteration = entry.get("iteration", "?")
        # Support both new format (tool_call.name) and legacy (tool)
        tc = entry.get("tool_call", {})
        tool = tc.get("name", entry.get("tool", "unknown"))
        args = tc.get("args", entry.get("args", {}))
        result = entry.get("observation", entry.get("result", ""))

        # Summarize args (show key info only)
        if isinstance(args, dict):
            args_summary = ", ".join(f"{k}={repr(v)[:50]}" for k, v in list(args.items())[:3])
            if len(args) > 3:
                args_summary += ", ..."
        else:
            args_summary = str(args)[:80]

        # Truncate result for display
        result_preview = str(result)[:100].replace('\n', ' ')
        if len(str(result)) > 100:
            result_preview += "..."

        lines.append(f"{i+1}. **[iter {iteration}]** `{tool}({args_summary})`")
        if result_preview:
            lines.append(f"   → {result_preview}")

    return "\n".join(lines)


def _format_exit_interview_result(result: dict) -> str:
    """Format exit_interview_result as structured fields."""
    if not isinstance(result, dict):
        return f"```\n{result}\n```"

    is_complete = result.get("is_complete", "?")
    reasoning = result.get("reasoning", "")
    missing = result.get("missing_elements", "")
    recommended = result.get("recommended_specialists", [])
    method = result.get("method", "")
    return_control = result.get("return_control", "")

    status = "✅ COMPLETE" if is_complete else "❌ INCOMPLETE"
    lines = [f"**Status:** {status}"]
    if method:
        lines.append(f"**Method:** {method}")
    if reasoning:
        lines.append(f"**Reasoning:** {reasoning}")
    if missing:
        lines.append(f"**Missing:** {missing}")
    if recommended:
        lines.append(f"**Recommended specialists:** {', '.join(recommended)}")
    if return_control:
        lines.append(f"**Return control mode:** {return_control}")

    return "\n".join(lines)


def _format_artifact(key: str, value) -> str:
    """
    Intelligently format an artifact based on its type and key.
    Returns formatted markdown string.
    """
    # resume_trace (or legacy research_trace_N) - format as tool call log
    if (key == "resume_trace" or key.startswith("research_trace_")) and isinstance(value, list):
        return _format_trace(value, key)

    # exit_interview_result - format as structured fields
    if key == "exit_interview_result" and isinstance(value, dict):
        return _format_exit_interview_result(value)

    # context_plan - pretty JSON
    if key == "context_plan" and isinstance(value, dict):
        return f"```json\n{json.dumps(value, indent=2, default=str)}\n```"

    # system_plan - pretty JSON
    if key == "system_plan" and isinstance(value, dict):
        return f"```json\n{json.dumps(value, indent=2, default=str)}\n```"

    # Other dicts/lists - pretty JSON with size limit
    if isinstance(value, (dict, list)):
        json_str = json.dumps(value, indent=2, default=str)
        if len(json_str) > 2000:
            json_str = json_str[:2000] + "\n... (truncated)"
        return f"```json\n{json_str}\n```"

    # Strings - as-is (with reasonable limit)
    content_str = str(value)
    if len(content_str) > 5000:
        content_str = content_str[:5000] + "\n... (truncated)"
    return f"```\n{content_str}\n```"


def generate_success_report(report_data: SuccessReport) -> str:
    """
    Takes a SuccessReport Pydantic model and formats it into a shareable
    Markdown string with intelligently formatted artifacts.
    """
    # Create a formatted string for artifacts, handling different types.
    artifacts_str = ""
    if report_data.artifacts:
        for key, value in report_data.artifacts.items():
            # Skip the final response artifact as it's displayed prominently elsewhere.
            if key == "final_user_response.md":
                continue

            # Handle Images
            if key.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) or (isinstance(value, str) and value.startswith('data:image')):
                # If it's a base64 string without the prefix, add it (assuming png for simplicity if unknown)
                image_src = value
                if isinstance(value, str) and not value.startswith('data:image') and not value.startswith('http'):
                     # Simple heuristic: if it's a long string without spaces, assume base64
                     if len(value) > 100 and ' ' not in value:
                         image_src = f"data:image/png;base64,{value}"

                artifacts_str += f"### 🖼️ {key}\n\n![{key}]({image_src})\n\n"
                continue

            # Handle archive paths - render as download links
            if key == "archive_package_path" and isinstance(value, str) and value.endswith(".zip"):
                # Extract just the filename from the path
                filename = os.path.basename(value)
                download_url = f"/v1/archives/{filename}"
                artifacts_str += f"### 📦 {key}\n\n[📥 Download Archive: {filename}]({download_url})\n\n"
                continue

            # Use intelligent formatting for all other artifacts
            formatted = _format_artifact(key, value)
            artifacts_str += f"### 📄 {key}\n\n{formatted}\n\n"

    if not artifacts_str:
        artifacts_str = "No additional artifacts were generated."

    report_parts = [
        f"# ✅ Agentic Workflow Report",
        f"- **Timestamp (UTC):** {report_data.timestamp.isoformat()}",
        f"- **Final Status:** Completed Successfully",
        "---",
        f"## 💬 Final User Response\n\n{report_data.final_user_response}",
        "---",
        f"## 🛤️ Routing History\n`{' -> '.join(report_data.routing_history) if report_data.routing_history else 'N/A'}`",
        "---",
        f"## 📦 Artifacts\n\n{artifacts_str.strip()}",
    ]
    return "\n\n".join(report_parts)