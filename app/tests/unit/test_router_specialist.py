# app/tests/unit/test_router_specialist.py
import pytest
import logging
from unittest.mock import MagicMock, patch, ANY, call
from langgraph.graph import END
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.router_specialist import (
    RouterSpecialist,
    _build_route_response_model,
)
from app.src.utils.errors import LLMInvocationError
from app.src.enums import CoreSpecialist
from app.src.graph.state_factory import create_test_state

@pytest.fixture
def router_specialist(initialized_specialist_factory):
    """Fixture for an initialized RouterSpecialist."""
    return initialized_specialist_factory("RouterSpecialist")

# --- Fine-Grained Unit Tests for Helper Methods ---

def test_get_available_specialists_no_recommendations(router_specialist):
    """Tests that all specialists are returned when no recommendations are present."""
    # Arrange
    router_specialist.set_specialist_map({
        "spec1": {"desc": "d1"},
        "spec2": {"desc": "d2"}
    })
    state = {"messages": []} # No recommended_specialists
    # Act
    available = router_specialist._get_available_specialists(state)
    # Assert
    assert "spec1" in available
    assert "spec2" in available
    assert len(available) == 2

def test_get_available_specialists_with_recommendations(router_specialist):
    """Tests that the specialist list is NOT filtered by recommendations (advisory mode).

    As of ADR-CORE-011, triage recommendations are advisory, not restrictive.
    The router always receives the full specialist list, with recommendations
    provided as context in the LLM prompt (see _get_llm_choice).
    """
    # Arrange
    router_specialist.set_specialist_map({
        "spec1": {"desc": "d1"},
        "spec2": {"desc": "d2"},
        "spec3": {"desc": "d3"}
    })
    state = {"recommended_specialists": ["spec1", "spec3"]}
    # Act
    available = router_specialist._get_available_specialists(state)
    # Assert: ALL specialists are available, regardless of recommendations
    assert "spec1" in available
    assert "spec2" in available  # Not filtered out
    assert "spec3" in available
    assert len(available) == 3  # All 3 specialists present

def test_handle_llm_failure_fallback_priority(router_specialist):
    """Tests the fallback logic when the LLM fails to make a decision."""
    # Case 1: Default Responder is available
    router_specialist.set_specialist_map({CoreSpecialist.DEFAULT_RESPONDER.value: {}, CoreSpecialist.ARCHIVER.value: {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == CoreSpecialist.DEFAULT_RESPONDER.value

    # Case 2: No Default Responder, Archiver is available
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == CoreSpecialist.ARCHIVER.value

    # Case 3: No fallbacks available
    router_specialist.set_specialist_map({"some_other_specialist": {}})
    result = router_specialist._handle_llm_failure()
    assert result["next_specialist"] == END

def test_validate_llm_choice_accept(router_specialist):
    """Valid string choice returns (choice, True)."""
    valid_options = ["spec1", "spec2"]
    choice, is_valid = router_specialist._validate_llm_choice("spec1", valid_options)
    assert choice == "spec1"
    assert is_valid is True

def test_validate_llm_choice_reject_string(router_specialist):
    """Invalid string choice returns (None, False) — no silent fallback."""
    valid_options = ["spec1", "spec2"]
    choice, is_valid = router_specialist._validate_llm_choice("invalid_spec", valid_options)
    assert choice is None
    assert is_valid is False

def test_validate_llm_choice_list_all_valid(router_specialist):
    """All-valid list passes through unchanged (no unwrapping)."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(["spec1", "spec2"], valid_options)
    assert choice == ["spec1", "spec2"]
    assert is_valid is True

def test_validate_llm_choice_list_preserves_single_item(router_specialist):
    """Single-item list is preserved as a list — no unwrapping to string."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(["spec1"], valid_options)
    assert choice == ["spec1"]
    assert is_valid is True
    assert isinstance(choice, list)

def test_validate_llm_choice_list_rejects_entirely_on_any_invalid(router_specialist):
    """Mixed valid/invalid list is rejected entirely — no partial filtering."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(
        ["spec1", "invalid_spec"], valid_options
    )
    assert choice is None
    assert is_valid is False

def test_validate_llm_choice_list_all_invalid(router_specialist):
    """All-invalid list returns (None, False)."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(
        ["invalid1", "invalid2"], valid_options
    )
    assert choice is None
    assert is_valid is False


def test_validate_deduplicates_list(router_specialist):
    """Duplicate specialist names are removed, preserving first-occurrence order (#219)."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(
        ["spec1", "spec2", "spec1", "spec2", "spec3"], valid_options
    )
    assert is_valid is True
    assert choice == ["spec1", "spec2", "spec3"]


def test_validate_all_available_selected_not_truncated(router_specialist):
    """Selecting all available specialists is valid — cap only fires above count (#219)."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(
        ["spec1", "spec2", "spec3"], valid_options
    )
    assert is_valid is True
    assert choice == ["spec1", "spec2", "spec3"]


def test_validate_dedup_and_cap_combined(router_specialist):
    """Duplicates removed first, then length capped (#219).

    Simulates the LFM2 failure: 12 entries from 8 available, with duplicates.
    After dedup, 6 unique valid entries remain — all within the 8-specialist cap.
    """
    valid_options = [
        "default_responder_specialist", "text_analysis_specialist",
        "navigator_browser_specialist", "chat_specialist",
        "web_builder", "image_specialist", "project_director", "tiered_synthesizer_specialist"
    ]
    llm_choice = [
        "default_responder_specialist", "text_analysis_specialist",
        "navigator_browser_specialist", "chat_specialist",
        "web_builder", "image_specialist",
        "navigator_browser_specialist", "text_analysis_specialist",
        "default_responder_specialist", "text_analysis_specialist",
        "web_builder", "image_specialist",
    ]
    choice, is_valid = router_specialist._validate_llm_choice(llm_choice, valid_options)
    assert is_valid is True
    # 6 unique entries from the 12, in first-occurrence order
    assert choice == [
        "default_responder_specialist", "text_analysis_specialist",
        "navigator_browser_specialist", "chat_specialist",
        "web_builder", "image_specialist",
    ]
    assert len(choice) == 6  # deduped from 12


def test_validate_preserves_valid_list(router_specialist):
    """Clean list without duplicates passes through unchanged (#219)."""
    valid_options = ["spec1", "spec2", "spec3"]
    choice, is_valid = router_specialist._validate_llm_choice(
        ["spec1", "spec3"], valid_options
    )
    assert is_valid is True
    assert choice == ["spec1", "spec3"]


# --- Integration-Style Tests for _execute_logic ---

def test_router_stage_3_termination_logic(router_specialist):
    """
    Tests Stage 3 of termination: when an archive report is present, the router
    should route to the special END node to terminate the graph.
    """
    # Arrange
    router_specialist.set_specialist_map({CoreSpecialist.ARCHIVER.value: {"description": "Archives things"}})
    state_after_archiver = create_test_state(
        messages=[
            HumanMessage(content="Do the thing."),
            AIMessage(
                content="Archive report generated.", name=CoreSpecialist.ARCHIVER.value
            ),
        ],
        turn_count=3,
        routing_history=["some_other_specialist", CoreSpecialist.ARCHIVER.value],
        artifacts={"archive_report.md": "This is the final report."}
    )

    # Act - Stage 3
    result = router_specialist._execute_logic(state_after_archiver)

    # Assert - Stage 3
    # The router should recognize the presence of the archive report and route to END.
    assert result["next_specialist"] == END


def test_router_normal_llm_routing(router_specialist):
    """
    Tests the primary path where the router uses the LLM to decide the next specialist.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    # Router now uses output_model_class (json_response) instead of tool_calls
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": ["file_specialist"]}
    }

    initial_state = create_test_state(
        messages=[HumanMessage(content="Please read my_file.txt")],
        turn_count=1,
        task_is_complete=False
    )

    # Act
    result = router_specialist._execute_logic(initial_state)

    # Assert
    mock_adapter.invoke.assert_called_once()
    assert result["next_specialist"] == "file_specialist"
    assert result.get("turn_count", 0) == 2
    ai_message = result["messages"][0]
    assert isinstance(ai_message, AIMessage)
    assert ai_message.additional_kwargs["routing_type"] == "llm_decision"
    assert "Routing to specialist: file_specialist" in ai_message.content

def test_router_handles_llm_invocation_error(router_specialist):
    """
    Tests that the router propagates an LLMInvocationError if the adapter fails.
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.side_effect = LLMInvocationError("API is down")

    initial_state = {"messages": [HumanMessage(content="Read a file")]}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        router_specialist._execute_logic(initial_state)

def test_router_handles_invalid_llm_response_with_retry(router_specialist):
    """Router retries once on invalid choice, then falls back to default_responder.

    With max_routing_retries=1 (default), the adapter is called twice:
    once for the initial invalid response, once for the retry (also invalid
    here because the mock always returns the same thing).
    """
    # Arrange
    router_specialist.set_specialist_map({"file_specialist": {"description": "File ops"}})

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": ["non_existent_specialist"]}
    }

    initial_state = {"messages": [HumanMessage(content="Do something weird")]}

    # Act
    result = router_specialist._execute_logic(initial_state)

    # Assert: 2 calls (initial + 1 retry)
    assert mock_adapter.invoke.call_count == 2
    assert result["next_specialist"] == CoreSpecialist.DEFAULT_RESPONDER.value
    ai_message = result["messages"][0]
    assert "Routing to specialist: default_responder_specialist" in ai_message.content
    assert ai_message.additional_kwargs["routing_type"] == "llm_decision"

def test_get_available_specialists_context_aware_filtering_with_tags(router_specialist):
    """Tests that context_engineering specialists are filtered out after context gathering.

    Note: Only "context_engineering" tag is filtered. "planning" tag specialists like
    systems_architect remain available as valid work destinations.
    """
    # Arrange
    router_specialist.set_specialist_map({
        "triage_architect": {"desc": "d1", "tags": ["context_engineering"]},
        "facilitator_specialist": {"desc": "d2", "tags": ["context_engineering"]},
        "systems_architect": {"desc": "d3", "tags": ["planning"]},
        "web_builder": {"desc": "d4", "tags": ["coding"]},
        "chat_specialist": {"desc": "d5", "tags": ["chat"]}
    })

    # Simulate context gathering complete
    state = {
        "messages": [],
        "artifacts": {"gathered_context": "Some context"}
    }

    # Act
    available = router_specialist._get_available_specialists(state)

    # Assert
    # Should filter out only "context_engineering" tagged specialists
    assert "triage_architect" not in available
    assert "facilitator_specialist" not in available

    # "planning" tag specialists remain available (valid work destinations)
    assert "systems_architect" in available
    assert "web_builder" in available
    assert "chat_specialist" in available
    assert len(available) == 3

def test_get_llm_choice_vision_logic_with_tags(router_specialist):
    """Tests that vision-capable specialists are identified via tags when an image is present."""
    # Arrange
    router_specialist.set_specialist_map({
        "text_only": {"desc": "d1", "tags": ["text"]},
        "vision_spec": {"desc": "d2", "tags": ["vision_capable"]},
        "researcher": {"desc": "d3", "tags": ["vision_capable"]}
    })
    
    state = {
        "messages": [HumanMessage(content="Look at this image")],
        "artifacts": {"uploaded_image.png": "some_image_data"},
        "scratchpad": {},
        "routing_history": []
    }
    
    mock_adapter = router_specialist.llm_adapter
    # Router now uses output_model_class (json_response) instead of tool_calls
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": ["vision_spec"]}
    }

    # Act
    router_specialist._get_llm_choice(state)

    # Assert
    # Check that the system message contains the recommendation for vision specialists
    call_args = mock_adapter.invoke.call_args
    request = call_args[0][0] # First arg is StandardizedLLMRequest
    system_msg = request.messages[-1].content
    
    assert "**CRITICAL: IMAGE DETECTED**" in system_msg
    
    # Extract the recommendation part to verify only vision specialists are recommended
    # Format: "... Recommended: spec1, spec2."
    if "Recommended:" in system_msg:
        recommendation_part = system_msg.split("Recommended:")[1].split(".")[0]
        assert "vision_spec" in recommendation_part
        assert "researcher" in recommendation_part
        assert "text_only" not in recommendation_part
    else:
        pytest.fail("Recommendation string not found in system message")

def test_get_llm_choice_dependency_logic_with_tags(router_specialist):
    """Tests that dependency logic correctly excludes planning specialists based on tags."""
    # Arrange
    router_specialist.set_specialist_map({
        "planner": {"desc": "d1", "tags": ["planning"]},
        "worker": {"desc": "d2", "tags": ["coding"]},
        "dependency_target": {"desc": "d3", "tags": ["coding"]},
        "alt_target": {"desc": "d4", "tags": ["coding"]}
    })

    # Scenario: 'worker' ran last, and recommends multiple targets.
    # 'planner' is in history but should be ignored for dependency check.
    # NOTE: Using 2+ recommendations forces LLM path (single recommendation uses deterministic routing)
    state = {
        "messages": [HumanMessage(content="Do work")],
        "artifacts": {},
        "scratchpad": {"recommended_specialists": ["dependency_target", "alt_target"]},
        "routing_history": ["planner", "worker"]
    }
    
    mock_adapter = router_specialist.llm_adapter
    # Router now uses output_model_class (json_response) instead of tool_calls
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": ["dependency_target"]}
    }

    # Act
    router_specialist._get_llm_choice(state)

    # Assert
    call_args = mock_adapter.invoke.call_args
    request = call_args[0][0]
    system_msg = request.messages[-1].content
    
    # Should identify 'worker' as the recommender, not 'planner'
    assert "**Dependency Requirement:**" in system_msg
    assert "The 'worker' specialist cannot proceed" in system_msg

# --- Enum-Constrained RouteResponse Tests ---

def test_build_route_response_model_produces_enum_schema():
    """Dynamic RouteResponse schema includes an enum array of valid specialist names."""
    valid_names = ["project_director", "chat_specialist", "web_builder"]
    model = _build_route_response_model(valid_names)
    schema = model.model_json_schema()

    # Navigate the JSON schema — items should have an enum
    items = schema["properties"]["next_specialist"]["items"]
    assert "enum" in items
    assert set(items["enum"]) == set(valid_names)

def test_build_route_response_model_rejects_invalid_on_parse():
    """Dynamic RouteResponse rejects names not in the enum during Pydantic validation."""
    valid_names = ["project_director", "chat_specialist"]
    model = _build_route_response_model(valid_names)

    # Valid parse
    obj = model(next_specialist=["project_director"])
    assert obj.next_specialist == ["project_director"]

    # Invalid parse
    with pytest.raises(Exception):  # ValidationError
        model(next_specialist=["project"])

def test_build_route_response_model_single_name():
    """Works correctly with a single specialist (edge case).

    Pydantic uses "const" instead of "enum" for single-value Literals,
    but LMStudio handles both — the constraint is still enforced.
    """
    model = _build_route_response_model(["only_specialist"])
    schema = model.model_json_schema()
    items = schema["properties"]["next_specialist"]["items"]
    # Pydantic uses "const" for single values, "enum" for multiple
    assert items.get("const") == "only_specialist" or items.get("enum") == ["only_specialist"]


# --- Semantic Retry Tests ---

def test_retry_fires_on_invalid_then_succeeds(router_specialist):
    """Adapter is called twice: invalid first, valid on retry."""
    router_specialist.set_specialist_map({
        "file_specialist": {"description": "File ops"},
        "chat_specialist": {"description": "Chat"},
    })

    mock_adapter = router_specialist.llm_adapter
    # First call: invalid name. Second call: valid name.
    mock_adapter.invoke.side_effect = [
        {"json_response": {"next_specialist": ["project"]}},
        {"json_response": {"next_specialist": ["file_specialist"]}},
    ]

    state = {
        "messages": [HumanMessage(content="Read my file")],
        "artifacts": {},
        "scratchpad": {},
        "routing_history": [],
    }

    result = router_specialist._get_llm_choice(state)

    assert mock_adapter.invoke.call_count == 2
    # Single-item list is unwrapped to string for downstream compatibility
    assert result["next_specialist"] == "file_specialist"

    # Verify correction message was appended on the retry call
    retry_request = mock_adapter.invoke.call_args_list[1][0][0]
    system_messages = [m for m in retry_request.messages if hasattr(m, 'content') and "not a valid specialist" in m.content]
    assert len(system_messages) == 1
    assert "'project'" in system_messages[0].content

def test_retry_disabled_when_max_retries_zero(router_specialist):
    """With max_routing_retries=0, invalid choice immediately falls through."""
    router_specialist.max_routing_retries = 0
    router_specialist.set_specialist_map({
        "file_specialist": {"description": "File ops"},
    })

    mock_adapter = router_specialist.llm_adapter
    mock_adapter.invoke.return_value = {
        "json_response": {"next_specialist": ["project"]}
    }

    state = {
        "messages": [HumanMessage(content="Read my file")],
        "artifacts": {},
        "scratchpad": {},
        "routing_history": [],
    }

    result = router_specialist._get_llm_choice(state)

    # Only 1 call — no retries
    assert mock_adapter.invoke.call_count == 1
    assert result["next_specialist"] == CoreSpecialist.DEFAULT_RESPONDER.value

def test_max_routing_retries_read_from_config(initialized_specialist_factory):
    """max_routing_retries is read from specialist_config, defaulting to 1."""
    router = initialized_specialist_factory("RouterSpecialist")
    # Default from conftest mock config (no max_routing_retries key) → 1
    assert router.max_routing_retries == 1


def setup_module(module):
    """Set up logging for the test module."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )


def teardown_module(module):
    """Teardown logging for the test module."""
    logging.shutdown()
