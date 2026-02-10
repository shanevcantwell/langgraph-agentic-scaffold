#!/usr/bin/env python3
"""
Archive analysis tool for LAS workflow debugging.

Usage:
    python scripts/analyze_archive.py <archive_path> [command]

Commands:
    summary     - Overview of the run (default)
    traces      - Show LLM traces with tool calls
    tools       - Count tool calls by type
    concurrency - Show concurrent batch analysis per iteration
    prompt <n>  - Show assembled prompt for trace step n
    compare <archive2> - Compare two archives
    ei          - Show Exit Interview details

Examples:
    python scripts/analyze_archive.py ./logs/archive/run_20260205_110024_9c03f0e0.zip
    python scripts/analyze_archive.py ./logs/archive/run_*.zip tools
    python scripts/analyze_archive.py ./logs/archive/run_*.zip concurrency
    python scripts/analyze_archive.py ./logs/archive/run_*.zip prompt 3
"""

import json
import sys
import zipfile
from pathlib import Path
from collections import Counter


def load_archive(path: str) -> dict:
    """Load all files from archive into a dict."""
    data = {}
    with zipfile.ZipFile(path, 'r') as zf:
        for name in zf.namelist():
            content = zf.read(name).decode('utf-8', errors='replace')
            if name.endswith('.json'):
                try:
                    data[name] = json.loads(content)
                except json.JSONDecodeError:
                    data[name] = content
            elif name.endswith('.jsonl'):
                lines = []
                for line in content.strip().split('\n'):
                    if line:
                        try:
                            lines.append(json.loads(line))
                        except json.JSONDecodeError:
                            lines.append({"raw": line})
                data[name] = lines
            else:
                data[name] = content
    return data


def cmd_summary(data: dict):
    """Print run summary."""
    manifest = data.get('manifest.json', {})
    print(f"Run ID: {manifest.get('run_id', '?')}")
    print(f"Timestamp: {manifest.get('timestamp', '?')}")
    print(f"Termination: {manifest.get('termination_reason', '?')}")

    # Routing history
    routing = manifest.get('routing_history', [])
    print(f"\nRouting ({len(routing)} steps):")
    print(f"  {' -> '.join(routing)}")

    # Artifacts
    artifacts = manifest.get('artifacts', [])
    print(f"\nArtifacts ({len(artifacts)}):")
    for a in artifacts:
        print(f"  - {a.get('filename', '?')} ({a.get('size_bytes', 0)} bytes)")

    # Tool call summary
    traces = data.get('llm_traces.jsonl', [])
    tool_counts = Counter()
    for trace in traces:
        # From research_trace in final_state
        pass

    final_state = data.get('final_state.json', {})
    artifacts_data = final_state.get('artifacts', {})

    # Find research_trace_N keys
    for key, value in artifacts_data.items():
        if key.startswith('research_trace') and isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and 'tool' in entry:
                    tool_counts[entry['tool']] += 1

    if tool_counts:
        print(f"\nTool calls:")
        for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            print(f"  {tool}: {count}")


def cmd_traces(data: dict):
    """Print LLM traces."""
    traces = data.get('llm_traces.jsonl', [])
    for i, trace in enumerate(traces):
        specialist = trace.get('specialist', '?')
        model = trace.get('model_id', '?')
        latency = trace.get('latency_ms', 0)
        tool_calls = trace.get('tool_calls', [])

        print(f"\n[{i}] {specialist} ({model}) - {latency}ms")

        if tool_calls:
            print(f"    Tool calls: {len(tool_calls)}")
            for tc in tool_calls[:5]:  # Limit display
                print(f"      - {tc.get('name', '?')}({list(tc.get('args', {}).keys())})")

        response = trace.get('response_text', '')
        if response:
            preview = response[:200].replace('\n', ' ')
            print(f"    Response: {preview}...")


def cmd_tools(data: dict):
    """Count all tool calls."""
    final_state = data.get('final_state.json', {})
    artifacts = final_state.get('artifacts', {})

    tool_counts = Counter()
    tool_examples = {}

    for key, value in artifacts.items():
        if key.startswith('research_trace') and isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and 'tool' in entry:
                    tool = entry['tool']
                    tool_counts[tool] += 1
                    if tool not in tool_examples:
                        tool_examples[tool] = entry.get('args', {})

    print("Tool call counts:")
    for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
        print(f"  {tool}: {count}")
        example = tool_examples.get(tool, {})
        if example:
            print(f"    Example args: {example}")

    total = sum(tool_counts.values())
    print(f"\nTotal: {total} tool calls")

    # Check for missing action tools
    has_move = 'move_file' in tool_counts
    has_create = 'create_directory' in tool_counts
    if not has_move and not has_create:
        print("\n⚠️  No filesystem modification tools called (move_file, create_directory)")


def cmd_concurrency(data: dict):
    """Show concurrent batch analysis per iteration.

    Groups trace entries by iteration number within each research_trace.
    Entries sharing the same iteration were dispatched concurrently via
    ThreadPoolExecutor in execute_with_tools().
    """
    final_state = data.get('final_state.json', {})
    artifacts = final_state.get('artifacts', {})

    trace_keys = sorted(
        k for k in artifacts if k.startswith('research_trace') and isinstance(artifacts[k], list)
    )

    if not trace_keys:
        print("No research traces found in artifacts.")
        return

    total_iterations = 0
    total_concurrent = 0

    for trace_key in trace_keys:
        entries = artifacts[trace_key]
        if not entries:
            continue

        print(f"\n=== {trace_key} ({len(entries)} tool calls) ===")

        # Group by iteration
        iter_groups: dict[int, list[dict]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            iteration = entry.get('iteration', -1)
            iter_groups.setdefault(iteration, []).append(entry)

        for iteration in sorted(iter_groups.keys()):
            group = iter_groups[iteration]
            tools = [e.get('tool') or e.get('tool_name', '?') for e in group]
            batch_size = len(group)

            marker = ""
            if batch_size > 1:
                marker = f"  <-- CONCURRENT ({batch_size})"
                total_concurrent += 1

            tools_str = ", ".join(tools)
            print(f"  iter {iteration:>2}: {tools_str}{marker}")
            total_iterations += 1

        # Per-trace stats
        concurrent_in_trace = sum(1 for g in iter_groups.values() if len(g) > 1)
        sequential_in_trace = sum(1 for g in iter_groups.values() if len(g) == 1)
        max_batch = max(len(g) for g in iter_groups.values()) if iter_groups else 0
        print(f"  ---")
        print(f"  {len(iter_groups)} iterations: {concurrent_in_trace} concurrent, {sequential_in_trace} sequential (max batch: {max_batch})")

    # Overall summary
    if len(trace_keys) > 1:
        print(f"\n--- Overall ---")
        print(f"  {total_iterations} total iterations across {len(trace_keys)} traces")
        print(f"  {total_concurrent} concurrent batches")


def cmd_prompt(data: dict, step: int):
    """Show assembled prompt for a specific trace step."""
    traces = data.get('llm_traces.jsonl', [])
    if step >= len(traces):
        print(f"Error: Step {step} not found (max: {len(traces)-1})")
        return

    trace = traces[step]
    print(f"=== Step {step}: {trace.get('specialist', '?')} ===")
    print(f"Model: {trace.get('model_id', '?')}")
    print(f"From: {trace.get('from_source', '?')}")
    print(f"Latency: {trace.get('latency_ms', 0)}ms")

    print("\n=== SYSTEM PROMPT ===")
    print(trace.get('system_prompt', '[none]'))

    print("\n=== ASSEMBLED PROMPT ===")
    print(trace.get('assembled_prompt', '[none]'))

    print("\n=== RESPONSE ===")
    print(trace.get('response_text', '[none]'))

    tool_calls = trace.get('tool_calls', [])
    if tool_calls:
        print(f"\n=== TOOL CALLS ({len(tool_calls)}) ===")
        for tc in tool_calls:
            print(f"  {tc.get('name', '?')}: {json.dumps(tc.get('args', {}), indent=4)}")


def cmd_compare(data1: dict, path2: str):
    """Compare two archives."""
    data2 = load_archive(path2)

    # Compare tool counts
    def get_tool_counts(data):
        final_state = data.get('final_state.json', {})
        artifacts = final_state.get('artifacts', {})
        counts = Counter()
        for key, value in artifacts.items():
            if key.startswith('research_trace') and isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict) and 'tool' in entry:
                        counts[entry['tool']] += 1
        return counts

    counts1 = get_tool_counts(data1)
    counts2 = get_tool_counts(data2)

    all_tools = set(counts1.keys()) | set(counts2.keys())

    print("Tool call comparison:")
    print(f"{'Tool':<20} {'Archive1':>10} {'Archive2':>10} {'Diff':>10}")
    print("-" * 52)
    for tool in sorted(all_tools):
        c1 = counts1.get(tool, 0)
        c2 = counts2.get(tool, 0)
        diff = c2 - c1
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        print(f"{tool:<20} {c1:>10} {c2:>10} {diff_str:>10}")

    print("-" * 52)
    print(f"{'TOTAL':<20} {sum(counts1.values()):>10} {sum(counts2.values()):>10}")


def cmd_ei(data: dict):
    """Show Exit Interview details."""
    traces = data.get('llm_traces.jsonl', [])

    for i, trace in enumerate(traces):
        if trace.get('specialist') == 'exit_interview_specialist':
            print(f"\n=== EI Invocation (step {i}) ===")
            print(f"Model: {trace.get('model_id', '?')}")

            prompt = trace.get('assembled_prompt', '')

            # Find Success Criteria section
            if '**Success Criteria:**' in prompt:
                start = prompt.find('**Success Criteria:**')
                end = prompt.find('**Planned Specialists', start)
                if end < 0:
                    end = start + 500
                print("\n--- Success Criteria ---")
                print(prompt[start:end])
            elif '**Exit Plan' in prompt:
                start = prompt.find('**Exit Plan')
                end = prompt.find('**Planned Specialists', start)
                if end < 0:
                    end = start + 500
                print("\n--- Exit Plan ---")
                print(prompt[start:end])
            else:
                print("\n⚠️  No exit plan/success criteria found in prompt")

            print("\n--- Response ---")
            print(trace.get('response_text', '[none]'))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    archive_path = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else 'summary'

    # Handle glob patterns
    if '*' in archive_path:
        import glob
        matches = sorted(glob.glob(archive_path))
        if not matches:
            print(f"No archives match: {archive_path}")
            sys.exit(1)
        archive_path = matches[-1]  # Most recent
        print(f"Using: {archive_path}\n")

    data = load_archive(archive_path)

    if command == 'summary':
        cmd_summary(data)
    elif command == 'traces':
        cmd_traces(data)
    elif command == 'tools':
        cmd_tools(data)
    elif command == 'concurrency':
        cmd_concurrency(data)
    elif command == 'prompt':
        step = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        cmd_prompt(data, step)
    elif command == 'compare':
        if len(sys.argv) < 4:
            print("Usage: analyze_archive.py <archive1> compare <archive2>")
            sys.exit(1)
        cmd_compare(data, sys.argv[3])
    elif command == 'ei':
        cmd_ei(data)
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
