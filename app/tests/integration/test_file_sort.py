"""
Integration tests for file sorting operations.

Progressive complexity from counting to full emergent sorting.

Run with: docker exec langgraph-app pytest app/tests/integration/test_file_sort.py -v
"""
import pytest
import random
from pathlib import Path
from fastapi.testclient import TestClient

from app.tests.helpers import (
    folder_of_empty_files,
    unique_test_folder,
    cleanup_folder,
)


@pytest.fixture(scope="module")
def initialized_app():
    """Provides an initialized FastAPI app with real graph and specialists."""
    from app.src import api
    return api.app


@pytest.fixture
def test_folder():
    """Create a unique test folder, clean up after test."""
    folder = unique_test_folder("sort_test")
    yield folder
    cleanup_folder(folder)


# =============================================================================
# Level 1: Count files in a folder
# =============================================================================

@pytest.mark.live_llm
@pytest.mark.integration
def test_count_files_in_folder(initialized_app, test_folder):
    """
    Prompt: "Count the files in folder X"
    Expected: Response contains the correct count.
    """
    num_files = random.randint(3, 7)
    folder_path = folder_of_empty_files(
        str(test_folder.relative_to(Path("workspace").resolve())),
        "file_{n}.txt",
        num_files,
    )
    folder_name = test_folder.name

    with TestClient(initialized_app) as client:
        response = client.post("/v1/graph/invoke", json={
            "input_prompt": f"Count the files in folder `{folder_name}`",
            "text_to_process": None,
            "image_to_process": None,
        })
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})

        # Collect all text from response
        artifacts = final_state.get("artifacts", {})
        messages = final_state.get("messages", [])

        response_text = ""
        if isinstance(artifacts, dict):
            response_text += artifacts.get("final_user_response.md", "")
        for msg in messages:
            if isinstance(msg, dict):
                response_text += " " + msg.get("content", "")

        # Debug output
        print(f"\n=== TEST: count_files_in_folder ===")
        print(f"Folder: {folder_name}")
        print(f"Expected count: {num_files}")
        print(f"Routing: {final_state.get('routing_history', [])}")
        print(f"Response: {response_text[:500]}")

        assert str(num_files) in response_text, (
            f"Expected count {num_files} not in response.\n"
            f"Files created: {num_files}\n"
            f"Response: {response_text[:500]}"
        )


# =============================================================================
# Triage Recommendation Tracking
# =============================================================================
# These tests validate that Triage recommends the correct specialist based on
# the verb (predicate) in the user's request, not just nouns (direct objects).
#
# Background: "Count files in X" was incorrectly routed to file_operations_specialist
# because triage fixated on "files" (noun) instead of "count" (verb = reasoning).
# Fix: Updated specialist descriptions with verb-based 1-shot examples.
# =============================================================================

@pytest.mark.live_llm
@pytest.mark.integration
def test_triage_recommends_chat_for_counting(initialized_app):
    """
    Triage should recommend chat_specialist for counting tasks (reasoning verb).

    The verb "count" indicates reasoning/analysis, not file operations.
    Triage's recommended_specialists should include chat_specialist.
    """
    with TestClient(initialized_app) as client:
        response = client.post("/v1/graph/invoke", json={
            "input_prompt": "Count how many files are in the workspace folder",
            "text_to_process": None,
            "image_to_process": None,
        })
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Debug output
        print(f"\n=== TEST: triage_recommends_chat_for_counting ===")
        print(f"Triage actions: {scratchpad.get('triage_actions', [])}")
        print(f"Triage reasoning: {scratchpad.get('triage_reasoning', '')}")
        print(f"Routing history: {final_state.get('routing_history', [])}")

        # Primary assertion: Router should route to chat subgraph for counting
        routing_history = final_state.get("routing_history", [])
        chat_subgraph_ran = any(
            s in routing_history for s in [
                "chat_specialist",
                "progenitor_alpha_specialist",
                "progenitor_bravo_specialist",
            ]
        )

        assert chat_subgraph_ran, (
            f"Expected chat subgraph for counting task.\n"
            f"Chat subgraph ran: {chat_subgraph_ran}\n"
            f"Routing history: {routing_history}"
        )

        # Secondary: If triage recommends anything, chat_specialist should be included
        if recommended:
            assert "chat_specialist" in recommended, (
                f"Triage recommended specialists but omitted chat_specialist.\n"
                f"Got: {recommended}"
            )


@pytest.mark.live_llm
@pytest.mark.integration
def test_triage_recommends_project_director_for_listing(initialized_app):
    """
    Triage should recommend project_director for file listing tasks.

    The verb "list" indicates file system operation, which routes to project_director
    per triage prompt: "Multi-step tasks, file operations, iteration → project_director"
    """
    with TestClient(initialized_app) as client:
        response = client.post("/v1/graph/invoke", json={
            "input_prompt": "List the files in the workspace folder",
            "text_to_process": None,
            "image_to_process": None,
        })
        assert response.status_code == 200

        result = response.json()
        final_state = result.get("final_output", {})
        artifacts = final_state.get("artifacts", {})
        scratchpad = final_state.get("scratchpad", {})

        # Debug output
        print(f"\n=== TEST: triage_recommends_project_director_for_listing ===")
        print(f"Triage actions: {scratchpad.get('triage_actions', [])}")
        print(f"Triage reasoning: {scratchpad.get('triage_reasoning', '')}")
        print(f"Routing history: {final_state.get('routing_history', [])}")

        # Primary assertion: Router should route to project_director for file listing
        routing_history = final_state.get("routing_history", [])
        project_director_ran = "project_director" in routing_history

        assert project_director_ran, (
            f"Expected project_director for file listing task.\n"
            f"Routing history: {routing_history}"
        )

        # Secondary: Triage should have recommended project_director
        if recommended:
            assert "project_director" in recommended, (
                f"Triage recommended specialists but omitted project_director.\n"
                f"Got: {recommended}"
            )
