#!/usr/bin/env python3
"""
Extract BFCL-formatted test cases from LAS archive traces.

Converts real execution traces from ./logs/archive/*.zip into
Berkeley Function Calling Leaderboard format for model evaluation.

Usage:
    python scripts/extract_bfcl_from_archives.py [--output OUTPUT_DIR] [--limit N]
"""

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib


# Tool schemas for specialists that use structured output
TOOL_SCHEMAS = {
    "triage_architect": {
        "name": "ContextPlan",
        "description": "Create a context acquisition plan",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": "Explanation of why these actions are needed"
                },
                "actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["research", "read_file", "summarize", "list_directory", "ask_user"]
                            },
                            "target": {"type": "string"},
                            "description": {"type": "string"},
                            "strategy": {"type": "string"}
                        },
                        "required": ["type", "target", "description"]
                    }
                },
                "recommended_specialists": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specialists to handle the task after context gathering"
                }
            },
            "required": ["reasoning", "actions", "recommended_specialists"]
        }
    },
    "router_specialist": {
        "name": "Route",
        "description": "Route to the next specialist(s)",
        "parameters": {
            "type": "object",
            "properties": {
                "next_specialists": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "One or more specialists to route to"
                }
            },
            "required": ["next_specialists"]
        }
    }
}


def extract_trace_from_archive(archive_path: Path) -> List[Dict]:
    """Extract llm_traces.jsonl from a zip archive."""
    traces = []
    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            if 'llm_traces.jsonl' in zf.namelist():
                with zf.open('llm_traces.jsonl') as f:
                    for line in f:
                        try:
                            traces.append(json.loads(line.decode('utf-8')))
                        except json.JSONDecodeError:
                            continue
    except zipfile.BadZipFile:
        pass
    return traces


def trace_to_bfcl(trace: Dict, archive_name: str) -> Optional[Dict]:
    """Convert a single trace to BFCL format."""
    specialist = trace.get("specialist", "")

    # Only process specialists with tool calls
    tool_calls = trace.get("tool_calls", [])
    if not tool_calls:
        return None

    # Get the tool schema for this specialist
    tool_schema = TOOL_SCHEMAS.get(specialist)
    if not tool_schema:
        return None

    # Build question (messages)
    question = []

    # System prompt
    system_prompt = trace.get("system_prompt", "")
    if system_prompt:
        question.append({"role": "system", "content": system_prompt})

    # User prompt
    assembled_prompt = trace.get("assembled_prompt", "")
    if assembled_prompt:
        question.append({"role": "user", "content": assembled_prompt})

    if not question:
        return None

    # Build ground truth from actual tool calls
    ground_truth = []
    for call in tool_calls:
        ground_truth.append({
            "name": call.get("name", ""),
            "arguments": call.get("args", {})
        })

    # Generate unique ID
    content_hash = hashlib.md5(
        (system_prompt + assembled_prompt).encode()
    ).hexdigest()[:8]
    test_id = f"{specialist}_{archive_name}_{content_hash}"

    return {
        "id": test_id,
        "question": question,
        "function": [tool_schema],
        "ground_truth": ground_truth,
        "metadata": {
            "specialist": specialist,
            "model_id": trace.get("model_id", "unknown"),
            "latency_ms": trace.get("latency_ms"),
            "timestamp": trace.get("timestamp"),
            "archive": archive_name,
            "step": trace.get("step")
        }
    }


def deduplicate_by_prompt(records: List[Dict]) -> List[Dict]:
    """Deduplicate records by (system_prompt, user_prompt) combination."""
    seen = set()
    unique = []

    for record in records:
        # Create a key from the question content
        question = record.get("question", [])
        system_content = ""
        user_content = ""
        for msg in question:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")[:500]  # First 500 chars
            elif msg.get("role") == "user":
                user_content = msg.get("content", "")

        key = (system_content, user_content)
        if key not in seen:
            seen.add(key)
            unique.append(record)

    return unique


def extract_all_archives(
    archive_dir: Path,
    output_dir: Path,
    limit: Optional[int] = None
) -> Dict[str, int]:
    """Extract BFCL records from all archives."""

    archives = sorted(archive_dir.glob("*.zip"))
    if limit:
        archives = archives[-limit:]  # Most recent N

    all_records = {
        "triage_architect": [],
        "router_specialist": []
    }

    for archive_path in archives:
        archive_name = archive_path.stem
        traces = extract_trace_from_archive(archive_path)

        for trace in traces:
            specialist = trace.get("specialist", "")
            if specialist in all_records:
                record = trace_to_bfcl(trace, archive_name)
                if record:
                    all_records[specialist].append(record)

    # Deduplicate and write output
    output_dir.mkdir(parents=True, exist_ok=True)
    stats = {}

    for specialist, records in all_records.items():
        unique_records = deduplicate_by_prompt(records)
        output_file = output_dir / f"{specialist}_bfcl.jsonl"

        with open(output_file, "w") as f:
            for record in unique_records:
                f.write(json.dumps(record) + "\n")

        stats[specialist] = len(unique_records)
        print(f"Wrote {len(unique_records)} records to {output_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Extract BFCL test cases from LAS archive traces"
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("./logs/archive"),
        help="Directory containing archive zip files"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("./app/tests/prompt-prix/extracted"),
        help="Output directory for BFCL files"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the N most recent archives"
    )

    args = parser.parse_args()

    if not args.archive_dir.exists():
        print(f"Archive directory not found: {args.archive_dir}")
        return 1

    stats = extract_all_archives(args.archive_dir, args.output, args.limit)

    print(f"\nExtraction complete:")
    for specialist, count in stats.items():
        print(f"  {specialist}: {count} unique test cases")

    return 0


if __name__ == "__main__":
    exit(main())
