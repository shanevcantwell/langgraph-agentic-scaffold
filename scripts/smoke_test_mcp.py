#!/usr/bin/env python3
"""
Smoke test for external MCP connectivity from the LAS container.

Tests async call_tool paths to prompt-prix and semantic-chunker MCP servers.
Run inside the langgraph-app container:
    docker exec langgraph-app python scripts/smoke_test_mcp.py

Optional: run only semantic-chunker tests:
    docker exec langgraph-app python scripts/smoke_test_mcp.py --semantic-chunker

Tests:
  prompt-prix:
    1. list_models — returns model manifest from LM Studio servers
    2. complete — single inference call to verify adapter chain
  semantic-chunker:
    3. calculate_drift (similar pair) — semantically close texts → low drift
    4. calculate_drift (dissimilar pair) — semantically distant texts → high drift
    5. calculate_drift (exemplar pair) — correct PD response vs exemplar → ~0.25-0.28

Note: sync_call_external_mcp cannot be tested from a standalone async script
because it uses run_coroutine_threadsafe to schedule on the "main loop" from a
worker thread. In this script we ARE the main loop, so it deadlocks. The sync
bridge works correctly in real specialist execution (ThreadPoolExecutor context).
"""
import asyncio
import json
import sys
import time
import yaml
from pathlib import Path


def parse_mcp_text(result) -> str | None:
    """Extract text from MCP CallToolResult."""
    if hasattr(result, 'content') and result.content:
        return result.content[0].text if hasattr(result.content[0], 'text') else str(result.content[0])
    return None


async def connect_service(client, service_name: str) -> list[str] | None:
    """Connect to an MCP service and return tool names."""
    print(f"--- Connecting to {service_name} MCP server ---")
    t0 = time.time()
    tools = await client.connect_from_config(service_name)
    elapsed = (time.time() - t0) * 1000

    if tools is None:
        print(f"FAIL: connect_from_config('{service_name}') returned None ({elapsed:.0f}ms)")
        return None

    print(f"OK: Connected in {elapsed:.0f}ms")
    print(f"Available tools ({len(tools)}):")
    for tool in sorted(tools):
        print(f"  - {tool}")
    print()
    return tools


async def test_prompt_prix(client):
    """Tests 1-2: prompt-prix MCP connectivity."""
    # Test 1: list_models
    print("--- Test 1: list_models (prompt-prix) ---")
    t0 = time.time()
    result = await client.call_tool("prompt-prix", "list_models", {})
    elapsed = (time.time() - t0) * 1000

    text = parse_mcp_text(result)
    if text:
        data = json.loads(text)
        model_count = len(data.get("models", []))
        server_count = len(data.get("servers", []))
        print(f"OK: {model_count} models across {server_count} servers ({elapsed:.0f}ms)")
        for m in data.get("models", [])[:3]:
            name = m if isinstance(m, str) else m.get("id", m.get("name", "?"))
            print(f"  - {name}")
        if model_count > 3:
            print(f"  ... and {model_count - 3} more")
    else:
        print(f"WARN: Unexpected result format: {type(result)}")
    print()

    # Test 2: complete (single inference)
    print("--- Test 2: complete (prompt-prix) ---")
    t0 = time.time()
    try:
        result = await client.call_tool("prompt-prix", "complete", {
            "messages": [
                {"role": "user", "content": "What is 2+2? Answer with just the number."}
            ],
            "model_id": "devstral-small-2-24b-instruct-2512",
            "max_tokens": 50
        })
        elapsed = (time.time() - t0) * 1000

        text = parse_mcp_text(result)
        if text:
            try:
                data = json.loads(text)
                response = data.get("response", data.get("text", text)) if isinstance(data, dict) else str(data)
            except json.JSONDecodeError:
                response = text
            print(f"OK: Response in {elapsed:.0f}ms")
            print(f"  Model response: {str(response)[:200]}")
        else:
            print(f"WARN: Unexpected result: {str(result)[:200]}")
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        print(f"FAIL: complete() raised {type(e).__name__}: {e} ({elapsed:.0f}ms)")
        print("  (May be expected if model isn't loaded on GPU)")
    print()


async def test_calculate_drift(client, test_num: int, label: str, text_a: str, text_b: str, expected_range: tuple[float, float] | None = None):
    """Run a single calculate_drift test against semantic-chunker MCP."""
    print(f"--- Test {test_num}: calculate_drift — {label} ---")
    t0 = time.time()
    try:
        result = await client.call_tool("semantic-chunker", "calculate_drift", {
            "text_a": text_a,
            "text_b": text_b,
        })
        elapsed = (time.time() - t0) * 1000

        text = parse_mcp_text(result)
        if text:
            try:
                data = json.loads(text)
                # graph_orchestrator.py:591 checks for "drift_score"
                drift = data.get("drift_score", data.get("drift", data.get("distance", "?")))
                range_str = ""
                if expected_range and isinstance(drift, (int, float)):
                    lo, hi = expected_range
                    in_range = lo <= drift <= hi
                    range_str = f"  {'PASS' if in_range else 'MISS'}: expected [{lo:.2f}, {hi:.2f}]"
                print(f"OK: drift = {drift} ({elapsed:.0f}ms)")
                if range_str:
                    print(range_str)
                print(f"  text_a: {text_a[:80]}")
                print(f"  text_b: {text_b[:80]}")
            except json.JSONDecodeError:
                print(f"OK: Raw result ({elapsed:.0f}ms): {text[:300]}")
        else:
            print(f"WARN: Unexpected result: {str(result)[:200]}")
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        print(f"FAIL: calculate_drift raised {type(e).__name__}: {e} ({elapsed:.0f}ms)")
    print()


async def test_semantic_chunker(client):
    """Tests 3-5: semantic-chunker MCP drift scoring."""

    # Test 3: Similar pair — should produce LOW drift
    await test_calculate_drift(
        client, 3, "similar pair (expect low drift)",
        text_a="The files have been organized into categories.",
        text_b="I've categorized all the documents into folders.",
        expected_range=(0.0, 0.20),
    )

    # Test 4: Dissimilar pair — should produce HIGH drift
    await test_calculate_drift(
        client, 4, "dissimilar pair (expect high drift)",
        text_a="The files have been organized into categories.",
        text_b="quantum entanglement enables faster-than-light communication between particles",
        expected_range=(0.40, 2.0),
    )

    # Test 5: PD exemplar pair — correct categorization vs exemplar
    # The sleeptime director compares model responses against exemplars.
    # Near-identical content with different phrasing → very low drift.
    exemplar = (
        'I\'ve organized the files into the following categories:\n'
        '- Documents: report.pdf, notes.txt\n'
        '- Images: photo.jpg, screenshot.png\n'
        '- Code: main.py, utils.js'
    )
    correct_response = (
        'I categorized your files into three groups:\n'
        '- Documents: report.pdf, notes.txt\n'
        '- Images: photo.jpg, screenshot.png\n'
        '- Code: main.py, utils.js'
    )
    wrong_response = (
        'I deleted all the files from the workspace directory. '
        'The filesystem is now clean and ready for new data.'
    )

    await test_calculate_drift(
        client, 5, "correct PD response vs exemplar (expect < 0.10)",
        text_a=exemplar,
        text_b=correct_response,
        expected_range=(0.0, 0.10),
    )

    await test_calculate_drift(
        client, 6, "WRONG PD response vs exemplar (expect > 0.28)",
        text_a=exemplar,
        text_b=wrong_response,
        expected_range=(0.28, 2.0),
    )

    # Test 7: Realistic battery pair — model uses different structure/wording
    # but achieves correct categorization. This is the ~0.25-0.28 calibration zone.
    different_correct = (
        'Done! Here\'s what I did:\n\n'
        'Created three directories and moved the files:\n'
        '1. docs/ — report.pdf, notes.txt\n'
        '2. media/ — photo.jpg, screenshot.png\n'
        '3. source/ — main.py, utils.js\n\n'
        'All 6 files have been categorized successfully.'
    )

    await test_calculate_drift(
        client, 7, "different-structure correct response (expect 0.15-0.35)",
        text_a=exemplar,
        text_b=different_correct,
        expected_range=(0.10, 0.35),
    )


async def main():
    # Parse args
    sc_only = "--semantic-chunker" in sys.argv or "--sc" in sys.argv

    # Load config
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("ERROR: config.yaml not found. Run from project root.")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Import and initialize client — constructor expects FULL app config
    from src.mcp.external_client import ExternalMcpClient
    client = ExternalMcpClient(config)

    # --- prompt-prix tests ---
    if not sc_only:
        pp_config = config.get("mcp", {}).get("external_mcp", {}).get("services", {}).get("prompt-prix", {})
        if pp_config.get("enabled"):
            tools = await connect_service(client, "prompt-prix")
            if tools:
                await test_prompt_prix(client)
        else:
            print("SKIP: prompt-prix not enabled in config.yaml\n")

    # --- semantic-chunker tests ---
    sc_config = config.get("mcp", {}).get("external_mcp", {}).get("services", {}).get("semantic-chunker", {})
    if sc_config.get("enabled"):
        tools = await connect_service(client, "semantic-chunker")
        if tools:
            await test_semantic_chunker(client)
    else:
        print("SKIP: semantic-chunker not enabled in config.yaml\n")

    print("--- Summary ---")
    print("All tests completed. Check results above for FAIL/WARN items.")
    print()
    print("Drift calibration reference (embeddinggemma-300m 768-d):")
    print("  < 0.10  = stutter (model cycling without progress)")
    print("  0.25-0.28 = correct file categorization (calibrated)")
    print("  0.30  = semantic squelch threshold")
    print("  > 0.40  = semantically distant / wrong answer")


if __name__ == "__main__":
    asyncio.run(main())
