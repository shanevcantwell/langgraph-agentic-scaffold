# Audited on Sept 23, 2025
# app/tests/unit/test_web_builder.py
import pytest
from unittest.mock import MagicMock
from app.src.specialists.web_builder import WebBuilder
from app.src.utils.errors import LLMInvocationError

@pytest.fixture
def specialist():
    """Fixture for an initialized WebBuilder with a mocked adapter."""
    s = WebBuilder("web_builder")
    s.llm_adapter = MagicMock()
    return s

def test_web_builder_single_cycle(specialist):
    """
    Tests the default behavior (1 cycle) where it generates HTML and signals completion.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site."} # No refinement_cycles key
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["html_artifact"] == mock_response["html_document"]
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state
    assert result_state["web_builder_iteration"] is None # Counter is cleaned up

def test_web_builder_multi_cycle_loop(specialist):
    """
    Tests the first iteration of a multi-cycle refinement, ensuring it recommends the critic.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Refined Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 0 # This is the first run
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert "task_is_complete" not in result_state
    assert result_state["recommended_specialists"] == ["critic_specialist"]
    assert result_state["web_builder_iteration"] == 1

def test_web_builder_multi_cycle_intermediate_loop(specialist):
    """
    Tests an intermediate iteration of a multi-cycle refinement, ensuring it recommends the critic.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Refined Hello Again</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 1 # This is the second run
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert "task_is_complete" not in result_state
    assert result_state["recommended_specialists"] == ["critic_specialist"]
    assert result_state["web_builder_iteration"] == 2

def test_web_builder_multi_cycle_final(specialist):
    """
    Tests the final iteration of a multi-cycle refinement, ensuring it signals completion.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Final Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 2 # This is the third and final run (0, 1, 2)
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state
    assert result_state["web_builder_iteration"] is None # Counter is cleaned up

def test_web_builder_handles_none_iteration_state(specialist):
    """
    Tests that the builder correctly handles the case where the iteration
    counter is explicitly set to None in the state, which happens on the
    first run.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site."},
        "web_builder_iteration": None # Explicitly set to None
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    # The main assertion is that this doesn't crash with a TypeError.
    specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["task_is_complete"] is True
    assert result_state["web_builder_iteration"] is None

def test_web_builder_handles_missing_system_plan(specialist):
    """Tests self-correction when the system_plan artifact is missing."""
    # Arrange
    initial_state = {"messages": []} # No system_plan

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_not_called()
    assert "I cannot run because there is no system plan" in result_state["messages"][0].content
    assert result_state["recommended_specialists"] == ["systems_architect"]

def test_web_builder_handles_llm_invocation_error(specialist):
    """Tests that an LLMInvocationError is propagated correctly."""
    # Arrange
    specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": [], "system_plan": {"description": "Make a site."}}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        specialist._execute_logic(initial_state)

@pytest.mark.parametrize("bad_response", [
    {"json_response": {"wrong_key": "no html"}},
    {"json_response": None},
    {"text_response": "just text"}
], ids=["wrong_key", "no_json", "text_response_instead"])
def test_web_builder_handles_malformed_llm_response(specialist, bad_response):
    """Tests that the specialist raises an error if the LLM response is malformed."""
    # Arrange
    specialist.llm_adapter.invoke.return_value = bad_response
    initial_state = {"messages": [], "system_plan": {"description": "Make a site."}}

    # Act & Assert
    with pytest.raises(ValueError, match="failed to get a valid HTML document"):
        specialist._execute_logic(initial_state)

def test_web_builder_with_zero_refinement_cycles(specialist):
    """Tests that refinement_cycles=0 behaves like a single-cycle run."""
    # Arrange
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 0}
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state