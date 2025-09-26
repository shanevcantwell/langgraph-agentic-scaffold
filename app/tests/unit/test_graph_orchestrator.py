# app/tests/unit/test_graph_orchestrator.py

from unittest.mock import MagicMock
import pytest

from app.src.workflow.graph_orchestrator import GraphOrchestrator
from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import SpecialistError
from app.src.enums import CoreSpecialist

@pytest.fixture
def orchestrator_instance():
    """Provides a GraphOrchestrator instance for testing."""
    config = {"workflow": {"max_loop_cycles": 3}}
    specialists = {}
    orchestrator = GraphOrchestrator(config, specialists)
    return orchestrator

def test_safe_executor_handles_specialist_exception(orchestrator_instance):
    """
    Tests that the create_safe_executor wrapper catches exceptions from a specialist
    and returns a state with a detailed error_report.
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "failing_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.side_effect = SpecialistError("Something went wrong!")

    safe_executor = orchestrator_instance.create_safe_executor(mock_specialist)
    initial_state = {"messages": [], "routing_history": ["start"]}

    # Act
    result = safe_executor(initial_state)

    # Assert
    assert "error" in result
    assert "error_report" in result
    assert isinstance(result["error"], str)
    assert "failing_specialist" in result["error"]
    assert isinstance(result["error_report"], str)
    assert "Traceback" in result["error_report"]
    assert "Something went wrong!" in result["error_report"]

def test_safe_executor_handles_generic_exception(orchestrator_instance):
    """
    Tests that the executor also catches generic exceptions and formats them correctly.
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "generic_failing_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.side_effect = ValueError("A generic error")

    safe_executor = orchestrator_instance.create_safe_executor(mock_specialist)
    initial_state = {"messages": [], "routing_history": ["start"]}

    # Act
    result = safe_executor(initial_state)

    # Assert
    assert "error" in result
    assert "error_report" in result
    assert "A generic error" in result["error_report"]

def test_safe_executor_success_path(orchestrator_instance):
    """Tests the safe_executor for a successful, non-error execution."""
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "test_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.return_value = {"artifacts": {"new_artifact.txt": "success"}}

    safe_executor = orchestrator_instance.create_safe_executor(mock_specialist)
    initial_state = {"artifacts": {}}

    # Act
    result = safe_executor(initial_state)

    # Assert
    assert result == {"artifacts": {"new_artifact.txt": "success"}}
    mock_specialist.execute.assert_called_once_with(initial_state)

def test_safe_executor_blocks_execution_on_missing_artifact(orchestrator_instance):
    """
    Tests that the safe_executor prevents a specialist from running if a required
    artifact is missing from the state.
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "artifact_requiring_specialist"
    mock_specialist.specialist_config = {
        "requires_artifacts": ["system_plan"],
        "artifact_providers": {"system_plan": "systems_architect"}
    }

    safe_executor = orchestrator_instance.create_safe_executor(mock_specialist)
    initial_state = {"messages": [], "turn_count": 1, "artifacts": {}}

    # Act
    result = safe_executor(initial_state)

    # Assert
    mock_specialist.execute.assert_not_called()
    
    # The create_missing_artifact_response is now part of the orchestrator
    expected_response = orchestrator_instance.create_missing_artifact_response(
        specialist_name="artifact_requiring_specialist",
        missing_artifacts=["system_plan"],
        recommended_specialists=["systems_architect"]
    )
    assert result == expected_response

def test_create_missing_artifact_response_format(orchestrator_instance):
    """Tests the specific format of the missing artifact response."""
    # Act
    response = orchestrator_instance.create_missing_artifact_response(
        specialist_name="test_specialist",
        missing_artifacts=["artifact1"],
        recommended_specialists=["provider_specialist"]
    )
    # Assert
    assert response["recommended_specialists"] == ["provider_specialist"]

def test_route_to_next_specialist_normal_route(orchestrator_instance):
    """Tests that the function returns the correct specialist name from the state."""
    state = {"next_specialist": "file_specialist", "turn_count": 1}
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "file_specialist"

def test_route_to_next_specialist_detects_loop(orchestrator_instance):
    """Tests that the function routes to END when a repeating loop is detected."""
    # Configure the instance for the test
    orchestrator_instance.max_loop_cycles = 3
    orchestrator_instance.min_loop_len = 2

    # This history represents a loop of ['A', 'B'] repeating 3 times.
    state = {
        "routing_history": ["C", "A", "B", "A", "B", "A", "B"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == CoreSpecialist.END.value

def test_route_to_next_specialist_loop_not_long_enough(orchestrator_instance):
    """Tests that a repeating pattern shorter than min_loop_len is not flagged as a loop."""
    orchestrator_instance.max_loop_cycles = 2
    orchestrator_instance.min_loop_len = 2 # A loop must be at least 2 specialists long

    # This history has a repeating 'A', but the loop length is only 1.
    state = {
        "routing_history": ["B", "A", "A", "A"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "some_specialist"

def test_route_to_next_specialist_allows_non_loop(orchestrator_instance):
    """Tests that the function does not halt for a non-looping history."""
    orchestrator_instance.max_loop_cycles = 2
    orchestrator_instance.min_loop_len = 2

    state = {
        "routing_history": ["A", "B", "C", "D"],
        "next_specialist": "some_specialist"
    }
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == "some_specialist"

def test_route_to_next_specialist_handles_no_route(orchestrator_instance):
    """Tests that the function routes to END if the router fails to provide a next step."""
    state = {"next_specialist": None, "turn_count": 1}
    result = orchestrator_instance.route_to_next_specialist(state)
    assert result == CoreSpecialist.END.value