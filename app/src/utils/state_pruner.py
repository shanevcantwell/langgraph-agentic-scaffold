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

def generate_success_report(report_data: SuccessReport) -> str:
    """
    Takes a SuccessReport Pydantic model and formats it into a shareable
    Markdown string.
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

            # Send full content - UI handles scrolling
            # Note: No HTML escaping needed - markdown code fences handle content literally
            content_str = str(value)
            artifacts_str += f"### 📄 {key}\n\n```\n{content_str}\n```\n\n"
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