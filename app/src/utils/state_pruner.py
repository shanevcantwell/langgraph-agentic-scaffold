# app/src/utils/state_pruner.py
import json
from typing import Dict, Any

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

    # Prune large artifacts
    if html := state.get("html_artifact"):
        pruned["html_artifact_preview"] = f"{html[:250]}..."

    if text := state.get("text_to_process"):
        pruned["text_to_process_preview"] = f"{text[:250]}..."

    # Include smaller, valuable artifacts as-is
    for key in ["system_plan", "critique_artifact", "extracted_data", "json_artifact"]:
        if value := state.get(key):
            pruned[key] = value

    # Include key metadata
    for key in ["turn_count", "next_specialist", "task_is_complete"]:
        if value := state.get(key):
            pruned[key] = value

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