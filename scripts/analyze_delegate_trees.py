#!/usr/bin/env python3
"""
Analyze delegate() call trees across LAS archives.

Reads all archives in logs/archive/, reconstructs parent→child trees,
and reports on tree shapes, depths, fan-out, timing, and anomalies.

Usage:
    python scripts/analyze_delegate_trees.py [archive_dir] [--tree RUN_ID] [--json]

Options:
    archive_dir     Path to archive directory (default: ./logs/archive)
    --tree RUN_ID   Print the full tree for a specific root run (8-char prefix OK)
    --json          Output structured JSON instead of human-readable text
    --orphans       Show child archives whose parent archive is missing
    --deepest N     Show the N deepest trees (default: 5)

Examples:
    python scripts/analyze_delegate_trees.py
    python scripts/analyze_delegate_trees.py --tree f16fb638
    python scripts/analyze_delegate_trees.py --orphans
    python scripts/analyze_delegate_trees.py ./logs/archive --deepest 10
"""

import json
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class RunNode:
    """A single run in the delegate tree."""

    def __init__(self, run_id: str, manifest: dict, archive_path: str):
        self.run_id = run_id
        self.parent_run_id: Optional[str] = manifest.get("parent_run_id")
        self.routing_history: List[str] = manifest.get("routing_history", [])
        self.termination_reason: str = manifest.get("termination_reason") or ""
        self.archive_path = archive_path
        self.children: List["RunNode"] = []

        # Timing
        self.timestamp_start = manifest.get("timestamp") or manifest.get("timestamp_start")
        self.timestamp_end = manifest.get("timestamp_end")

        # Artifacts metadata
        artifacts = manifest.get("artifacts", {})
        if isinstance(artifacts, dict):
            self.artifact_keys = list(artifacts.keys()) if isinstance(next(iter(artifacts.values()), None), dict) else list(artifacts.keys())
            self.artifact_count = len(self.artifact_keys)
        elif isinstance(artifacts, list):
            self.artifact_keys = [a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in artifacts]
            self.artifact_count = len(artifacts)
        else:
            self.artifact_keys = []
            self.artifact_count = 0

        self.final_response = manifest.get("final_response_generated", False)

    @property
    def short_id(self) -> str:
        return self.run_id[:8]

    @property
    def route_summary(self) -> str:
        """Compact routing summary."""
        cleaned = [r.replace("_specialist", "").replace("_", " ") for r in self.routing_history]
        if len(cleaned) <= 4:
            return " → ".join(cleaned)
        return " → ".join(cleaned[:2]) + f" → ... → " + " → ".join(cleaned[-2:])

    @property
    def outcome(self) -> str:
        """Classify the run outcome."""
        reason = self.termination_reason.lower()
        if not reason or reason == "success":
            return "success"
        if "loop" in reason or "stuck" in reason or "stagnation" in reason:
            return "stagnation"
        if "error" in reason or "fail" in reason:
            return "error"
        if "cancelled" in reason or "abort" in reason:
            return "cancelled"
        return "other"

    @property
    def latency_s(self) -> Optional[float]:
        """Wall time in seconds, if timestamps available."""
        if not self.timestamp_start or not self.timestamp_end:
            return None
        try:
            # Handle both ISO format and epoch
            if isinstance(self.timestamp_start, (int, float)):
                return self.timestamp_end - self.timestamp_start
            start = datetime.fromisoformat(self.timestamp_start.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.timestamp_end.replace("Z", "+00:00"))
            return (end - start).total_seconds()
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Tree construction
# ---------------------------------------------------------------------------

def load_manifests(archive_dir: str) -> Dict[str, RunNode]:
    """Load all manifests from archive zips, return dict keyed by run_id."""
    nodes: Dict[str, RunNode] = {}
    archive_path = Path(archive_dir)

    for zp in sorted(archive_path.glob("run_*.zip")):
        try:
            with zipfile.ZipFile(zp) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                run_id = manifest.get("run_id", "")
                if run_id:
                    nodes[run_id] = RunNode(run_id, manifest, str(zp))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as e:
            print(f"  WARN: Skipping {zp.name}: {e}", file=sys.stderr)

    return nodes


def build_trees(nodes: Dict[str, RunNode]) -> Tuple[List[RunNode], List[RunNode]]:
    """
    Link parent→child relationships. Returns (roots, orphans).

    Roots: nodes with no parent (or parent not in archive set).
    Orphans: child nodes whose parent archive is missing.
    """
    roots = []
    orphans = []

    for node in nodes.values():
        if node.parent_run_id:
            parent = nodes.get(node.parent_run_id)
            if parent:
                parent.children.append(node)
            else:
                orphans.append(node)
        else:
            roots.append(node)

    return roots, orphans


def tree_depth(node: RunNode) -> int:
    """Max depth of the subtree rooted at node."""
    if not node.children:
        return 0
    return 1 + max(tree_depth(c) for c in node.children)


def tree_size(node: RunNode) -> int:
    """Total number of nodes in the subtree."""
    return 1 + sum(tree_size(c) for c in node.children)


def tree_leaf_count(node: RunNode) -> int:
    """Number of leaf nodes (no children)."""
    if not node.children:
        return 1
    return sum(tree_leaf_count(c) for c in node.children)


def collect_outcomes(node: RunNode) -> Dict[str, int]:
    """Count outcomes across all nodes in the subtree."""
    counts = defaultdict(int)
    counts[node.outcome] += 1
    for child in node.children:
        for outcome, count in collect_outcomes(child).items():
            counts[outcome] += count
    return dict(counts)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

OUTCOME_SYMBOLS = {
    "success": "✓",
    "stagnation": "⟳",
    "error": "✗",
    "cancelled": "⊘",
    "other": "?",
}


def render_tree(node: RunNode, prefix: str = "", is_last: bool = True, depth: int = 0) -> str:
    """Render a tree as an indented ASCII diagram."""
    connector = "└── " if is_last else "├── "
    if depth == 0:
        line = ""
    else:
        line = prefix + connector

    symbol = OUTCOME_SYMBOLS.get(node.outcome, "?")
    latency = f" ({node.latency_s:.1f}s)" if node.latency_s else ""
    fan = f" [fan-out: {len(node.children)}]" if node.children else ""

    line += f"{symbol} {node.short_id} {node.route_summary}{latency}{fan}"

    if node.outcome not in ("success",) and node.termination_reason:
        reason_short = node.termination_reason[:80].replace("\n", " ")
        line += f"\n{prefix}{'    ' if is_last else '│   '}  reason: {reason_short}"

    lines = [line]

    child_prefix = prefix + ("    " if is_last else "│   ")
    for i, child in enumerate(node.children):
        is_child_last = (i == len(node.children) - 1)
        lines.append(render_tree(child, child_prefix, is_child_last, depth + 1))

    return "\n".join(lines)


def render_tree_json(node: RunNode) -> dict:
    """Render tree as nested JSON."""
    return {
        "run_id": node.run_id,
        "short_id": node.short_id,
        "routing_history": node.routing_history,
        "outcome": node.outcome,
        "termination_reason": node.termination_reason[:200] if node.termination_reason else None,
        "latency_s": node.latency_s,
        "artifact_count": node.artifact_count,
        "final_response": node.final_response,
        "fan_out": len(node.children),
        "children": [render_tree_json(c) for c in node.children],
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def report_summary(nodes: Dict[str, RunNode], roots: List[RunNode], orphans: List[RunNode]):
    """Print overall statistics."""
    total = len(nodes)
    children = [n for n in nodes.values() if n.parent_run_id]
    delegate_roots = [r for r in roots if r.children]

    print("=" * 70)
    print("DELEGATE TREE ANALYSIS")
    print("=" * 70)
    print(f"\nTotal archives:           {total}")
    print(f"Root runs (no parent):    {len(roots)}")
    print(f"Child runs (has parent):  {len(children)}")
    print(f"Orphan children:          {len(orphans)}")
    print(f"Roots with delegates:     {len(delegate_roots)}")

    if not delegate_roots:
        print("\nNo delegate trees found.")
        return

    # Depth distribution
    depths = {r.run_id: tree_depth(r) for r in delegate_roots}
    max_depth = max(depths.values())
    print(f"\nMax tree depth:           {max_depth}")
    print(f"Depth distribution:")
    for d in range(1, max_depth + 1):
        count = sum(1 for v in depths.values() if v == d)
        if count:
            print(f"  depth {d}: {count} trees")

    # Fan-out distribution
    fan_outs = []
    def collect_fan_outs(node):
        if node.children:
            fan_outs.append(len(node.children))
        for c in node.children:
            collect_fan_outs(c)
    for r in delegate_roots:
        collect_fan_outs(r)

    if fan_outs:
        print(f"\nFan-out statistics:")
        print(f"  max:  {max(fan_outs)}")
        print(f"  mean: {sum(fan_outs)/len(fan_outs):.1f}")
        print(f"  distribution: {dict(sorted(((fo, fan_outs.count(fo)) for fo in set(fan_outs))))}")

    # Outcome distribution across all children
    all_outcomes = defaultdict(int)
    for r in delegate_roots:
        for outcome, count in collect_outcomes(r).items():
            all_outcomes[outcome] += count

    print(f"\nOutcome distribution (all nodes in delegate trees):")
    for outcome, count in sorted(all_outcomes.items(), key=lambda x: -x[1]):
        symbol = OUTCOME_SYMBOLS.get(outcome, "?")
        print(f"  {symbol} {outcome}: {count}")

    # Size distribution
    sizes = [(r.short_id, tree_size(r)) for r in delegate_roots]
    sizes.sort(key=lambda x: -x[1])
    print(f"\nLargest trees (total nodes):")
    for sid, size in sizes[:5]:
        print(f"  {sid}: {size} nodes")


def report_trees(roots: List[RunNode], n: int = 5):
    """Print the deepest/widest trees."""
    delegate_roots = [r for r in roots if r.children]
    if not delegate_roots:
        print("No delegate trees found.")
        return

    # Sort by depth (primary), then size (secondary)
    scored = [(tree_depth(r), tree_size(r), r) for r in delegate_roots]
    scored.sort(key=lambda x: (-x[0], -x[1]))

    print(f"\n{'=' * 70}")
    print(f"TOP {min(n, len(scored))} DELEGATE TREES")
    print(f"{'=' * 70}")

    for i, (depth, size, root) in enumerate(scored[:n]):
        outcomes = collect_outcomes(root)
        outcome_str = ", ".join(f"{OUTCOME_SYMBOLS.get(k, '?')}{k}:{v}" for k, v in sorted(outcomes.items()))
        print(f"\n--- Tree {i+1}: depth={depth}, size={size}, outcomes=[{outcome_str}] ---\n")
        print(render_tree(root))
        print()


def report_orphans(orphans: List[RunNode]):
    """Show orphaned child archives."""
    if not orphans:
        print("\nNo orphaned children found.")
        return

    print(f"\n{'=' * 70}")
    print(f"ORPHANED CHILDREN ({len(orphans)})")
    print(f"{'=' * 70}")
    print("These archives have parent_run_id set but the parent archive is missing.\n")

    for o in orphans:
        symbol = OUTCOME_SYMBOLS.get(o.outcome, "?")
        print(f"  {symbol} {o.short_id} parent={o.parent_run_id[:8]} {o.route_summary}")
        if o.outcome != "success":
            print(f"    reason: {o.termination_reason[:80]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]

    # Parse options
    archive_dir = "./logs/archive"
    show_tree_id = None
    use_json = False
    show_orphans = False
    deepest_n = 5

    i = 0
    while i < len(args):
        if args[i] == "--tree" and i + 1 < len(args):
            show_tree_id = args[i + 1]
            i += 2
        elif args[i] == "--json":
            use_json = True
            i += 1
        elif args[i] == "--orphans":
            show_orphans = True
            i += 1
        elif args[i] == "--deepest" and i + 1 < len(args):
            deepest_n = int(args[i + 1])
            i += 2
        elif not args[i].startswith("--"):
            archive_dir = args[i]
            i += 1
        else:
            print(f"Unknown option: {args[i]}", file=sys.stderr)
            i += 1

    # Load and build
    print(f"Loading archives from {archive_dir}...", file=sys.stderr)
    nodes = load_manifests(archive_dir)
    print(f"Loaded {len(nodes)} manifests.", file=sys.stderr)

    roots, orphans = build_trees(nodes)

    # --tree: show specific tree
    if show_tree_id:
        # Find by prefix match
        matches = [n for rid, n in nodes.items() if rid.startswith(show_tree_id)]
        if not matches:
            print(f"No run found matching '{show_tree_id}'", file=sys.stderr)
            sys.exit(1)

        target = matches[0]

        # Walk up to root
        while target.parent_run_id and target.parent_run_id in nodes:
            target = nodes[target.parent_run_id]

        if use_json:
            print(json.dumps(render_tree_json(target), indent=2))
        else:
            depth = tree_depth(target)
            size = tree_size(target)
            outcomes = collect_outcomes(target)
            outcome_str = ", ".join(f"{k}:{v}" for k, v in sorted(outcomes.items()))
            print(f"Tree for {target.short_id}: depth={depth}, size={size}, outcomes=[{outcome_str}]\n")
            print(render_tree(target))
        return

    # Default: summary + top trees
    if use_json:
        delegate_roots = [r for r in roots if r.children]
        scored = sorted(delegate_roots, key=lambda r: (-tree_depth(r), -tree_size(r)))
        output = {
            "total_archives": len(nodes),
            "root_runs": len(roots),
            "child_runs": sum(1 for n in nodes.values() if n.parent_run_id),
            "orphans": len(orphans),
            "trees": [render_tree_json(r) for r in scored[:deepest_n]],
        }
        print(json.dumps(output, indent=2))
    else:
        report_summary(nodes, roots, orphans)
        report_trees(roots, deepest_n)
        if show_orphans:
            report_orphans(orphans)


if __name__ == "__main__":
    main()
