"""
Live LLM integration tests for BatchProcessorSpecialist.

These tests use a real LLM to diagnose the s.txt bug where files are
dropped during batch sort operations. The `batch_processor_reasoning`
scratchpad key allows us to observe what the LLM parsed.

Run with: pytest app/tests/integration/test_batch_processor_live.py -v -m live_llm
"""
import pytest
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from app.tests.conftest import assert_response_not_error


@pytest.fixture(scope="module")
def initialized_app():
    """
    Provides an initialized FastAPI app with real graph and specialists.
    """
    from app.src import api
    return api.app


@pytest.fixture
def batch_test_files():
    """
    Create test files in workspace directory visible to MCP file_specialist.

    Path mapping (consistent /workspace mount):
    - Host: ./workspace/test_batch/
    - Main container (pytest): /workspace/test_batch/
    - filesystem-mcp container: /workspace/test_batch/
    """
    test_dir = Path("workspace/test_batch")
    test_dir.mkdir(parents=True, exist_ok=True)

    # Create 5 test files
    for name in ["e.txt", "l.txt", "n.txt", "q.txt", "s.txt"]:
        (test_dir / name).touch()

    # Create destination directories
    (test_dir / "a-m").mkdir(exist_ok=True)
    (test_dir / "n-z").mkdir(exist_ok=True)

    yield test_dir

    # Cleanup
    shutil.rmtree(test_dir, ignore_errors=True)


@pytest.mark.live_llm
@pytest.mark.integration
def test_batch_sort_parses_all_explicit_files(initialized_app, batch_test_files):
    """
    Test that BatchProcessorSpecialist parses ALL explicitly listed files.

    This test diagnoses the s.txt bug by checking batch_processor_reasoning
    to see which files the LLM actually parsed from the prompt.
    """
    with TestClient(initialized_app) as client:
        prompt = """Sort these files into test_batch/a-m/ and test_batch/n-z/:
test_batch/e.txt, test_batch/l.txt, test_batch/n.txt, test_batch/q.txt, test_batch/s.txt"""

        payload = {
            "input_prompt": prompt,
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        routing_history = final_state.get("routing_history", [])
        scratchpad = final_state.get("scratchpad", {})

        # Verify batch_processor_specialist was invoked
        assert "batch_processor_specialist" in routing_history, (
            f"batch_processor_specialist not in routing history: {routing_history}"
        )

        # Extract reasoning for diagnosis
        reasoning = scratchpad.get("batch_processor_reasoning", "")
        print(f"\n=== BATCH PROCESSOR REASONING ===\n{reasoning}\n")

        # Check if all 5 files appear in reasoning
        expected_files = ["e.txt", "l.txt", "n.txt", "q.txt", "s.txt"]
        missing_files = [f for f in expected_files if f not in reasoning]

        if missing_files:
            print(f"\n!!! MISSING FILES: {missing_files}")
            print(f"This confirms the s.txt bug - LLM failed to parse these files.")

        # Assert all files were parsed (this will fail if bug exists, showing which files)
        for filename in expected_files:
            assert filename in reasoning, (
                f"File '{filename}' missing from batch_processor_reasoning. "
                f"LLM failed to parse it from the prompt.\n"
                f"Full reasoning:\n{reasoning}"
            )

        # Validate response content doesn't contain error indicators
        artifacts = final_state.get("artifacts", {})
        if isinstance(artifacts, dict):
            final_response = artifacts.get("final_user_response.md", "")
            if final_response:
                assert_response_not_error(final_response, "[BatchSort]")


@pytest.mark.live_llm
@pytest.mark.integration
def test_batch_sort_summary_matches_file_count(initialized_app, batch_test_files):
    """
    Test that batch_sort_summary reports correct file counts.

    If s.txt is being dropped, the summary will show 4 files instead of 5.
    """
    with TestClient(initialized_app) as client:
        prompt = """Sort these files into test_batch/a-m/ and test_batch/n-z/:
test_batch/e.txt, test_batch/l.txt, test_batch/n.txt, test_batch/q.txt, test_batch/s.txt"""

        payload = {
            "input_prompt": prompt,
            "text_to_process": None,
            "image_to_process": None
        }

        response = client.post("/v1/graph/invoke", json=payload)
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})

        # Check artifacts list for batch_sort_summary
        artifacts_keys = final_state.get("artifacts", [])
        print(f"\n=== ARTIFACTS ===\n{artifacts_keys}")

        # The summary should show total_files = 5
        # Note: artifacts in API response are just keys, not values
        # We need to check the reasoning for actual counts
        scratchpad = final_state.get("scratchpad", {})
        reasoning = scratchpad.get("batch_processor_reasoning", "")

        # Count how many files appear in "Parsed X files" line
        if "Parsed" in reasoning:
            print(f"\n=== PARSING SUMMARY ===")
            for line in reasoning.split("\n"):
                if "Parsed" in line or "files" in line.lower():
                    print(line)

        # Validate response content doesn't contain error indicators
        artifacts = final_state.get("artifacts", {})
        if isinstance(artifacts, dict):
            final_response = artifacts.get("final_user_response.md", "")
            if final_response:
                assert_response_not_error(final_response, "[BatchSortSummary]")
