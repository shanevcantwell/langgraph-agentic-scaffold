#!/usr/bin/env python
import ast
import os
from pathlib import Path


def summarize_tests(start_dir: str, output_file: str):
    """
    Parses Python test files to extract test function names and their docstrings,
    then writes a summary to a markdown file.
    """
    project_root = Path(__file__).parent.parent
    search_path = project_root / start_dir
    output_path = project_root / output_file

    # First pass: collect counts by category
    counts = {
        "unit": {"files": 0, "tests": 0},
        "integration": {"files": 0, "tests": 0},
        "other": {"files": 0, "tests": 0},
    }

    for root, _, files in os.walk(search_path):
        for file in files:
            if file.startswith("test_") and file.endswith(".py"):
                file_path = Path(root) / file
                relative_path = str(file_path.relative_to(project_root))

                # Determine category
                if "/unit/" in relative_path:
                    category = "unit"
                elif "/integration/" in relative_path:
                    category = "integration"
                else:
                    category = "other"

                counts[category]["files"] += 1

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()
                        tree = ast.parse(source)
                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                                counts[category]["tests"] += 1
                except Exception:
                    pass

    # Build summary with counts header
    total_files = sum(c["files"] for c in counts.values())
    total_tests = sum(c["tests"] for c in counts.values())

    summary_lines = [
        "# Test Suite Summary\n",
        "## Overview\n",
        "| Category | Files | Tests |",
        "|----------|-------|-------|",
        f"| Unit | {counts['unit']['files']} | {counts['unit']['tests']} |",
        f"| Integration | {counts['integration']['files']} | {counts['integration']['tests']} |",
    ]

    if counts["other"]["files"] > 0:
        summary_lines.append(f"| Other | {counts['other']['files']} | {counts['other']['tests']} |")

    summary_lines.extend([
        f"| **Total** | **{total_files}** | **{total_tests}** |",
        "",
    ])

    # Second pass: detailed listing
    for root, _, files in os.walk(search_path):
        for file in sorted(files):
            if file.startswith("test_") and file.endswith(".py"):
                file_path = Path(root) / file
                relative_path = file_path.relative_to(project_root)
                summary_lines.append(f"\n## `{relative_path}`\n")

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()
                        tree = ast.parse(source)

                        for node in ast.walk(tree):
                            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                                docstring = ast.get_docstring(node)
                                summary_lines.append(f"- **`{node.name}`**")
                                if docstring:
                                    # Clean up the docstring for single-line display
                                    first_line = docstring.strip().split("\n")[0]
                                    summary_lines.append(f"  - *{first_line}*")
                except Exception as e:
                    summary_lines.append(f"- Error parsing file: {e}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines))

    print(f"✅ Test suite summary generated at: {output_path}")


if __name__ == "__main__":
    # Configuration
    TEST_DIRECTORY = "app/tests"
    OUTPUT_MARKDOWN_FILE = "docs/generated/TEST_SUITE_SUMMARY.md"

    summarize_tests(TEST_DIRECTORY, OUTPUT_MARKDOWN_FILE)