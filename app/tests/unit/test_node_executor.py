# app/tests/unit/test_node_executor.py

from unittest.mock import MagicMock
import pytest

from app.src.workflow.executors.node_executor import NodeExecutor
from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import SpecialistError
from app.src.graph.state_factory import create_test_state

@pytest.fixture
def node_executor_instance():
    """Provides a NodeExecutor instance for testing."""
    config = {}
    return NodeExecutor(config)

def test_safe_executor_handles_specialist_exception(node_executor_instance):
    """
    Tests that the create_safe_executor wrapper catches exceptions from a specialist
    and returns a state with a detailed error_report.
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "failing_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.side_effect = SpecialistError("Something went wrong!")

    safe_executor = node_executor_instance.create_safe_executor(mock_specialist)
    initial_state = {
        "messages": [],
        "routing_history": ["start"],
        "turn_count": 0,
        "task_is_complete": False,
        "artifacts": {},
        "scratchpad": {}
    }

    # Act
    result = safe_executor(initial_state)

    # Assert
    assert "error" in result
    # Task 2.7: error_report moved to scratchpad
    assert "scratchpad" in result and "error_report" in result["scratchpad"]
    assert isinstance(result["error"], str)
    assert "failing_specialist" in result["error"]
    assert isinstance(result["scratchpad"]["error_report"], str)
    assert "Traceback" in result["scratchpad"]["error_report"]
    assert "Something went wrong!" in result["scratchpad"]["error_report"]

def test_safe_executor_handles_generic_exception(node_executor_instance):
    """
    Tests that the executor also catches generic exceptions and formats them correctly.
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "generic_failing_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.side_effect = ValueError("A generic error")

    safe_executor = node_executor_instance.create_safe_executor(mock_specialist)
    initial_state = {
        "messages": [],
        "routing_history": ["start"],
        "turn_count": 0,
        "task_is_complete": False,
        "artifacts": {},
        "scratchpad": {}
    }

    # Act
    result = safe_executor(initial_state)

    # Assert
    assert "error" in result
    # Task 2.7: error_report moved to scratchpad
    assert "scratchpad" in result and "error_report" in result["scratchpad"]
    assert "A generic error" in result["scratchpad"]["error_report"]

def test_safe_executor_success_path(node_executor_instance):
    """Tests the safe_executor for a successful, non-error execution."""
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "test_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.return_value = {"artifacts": {"new_artifact.txt": "success"}}

    safe_executor = node_executor_instance.create_safe_executor(mock_specialist)
    initial_state = {
        "artifacts": {},
        "messages": [],
        "routing_history": [],
        "turn_count": 0,
        "task_is_complete": False,
        "scratchpad": {}
    }

    # Act
    result = safe_executor(initial_state)

    # Assert
    # Task 2.7: safe_executor now adds routing_history centrally
    assert result["artifacts"] == {"new_artifact.txt": "success"}
    assert result["routing_history"] == ["test_specialist"]
    mock_specialist.execute.assert_called_once_with(initial_state)

def test_safe_executor_blocks_execution_on_missing_artifact(node_executor_instance):
    """
    Tests that the safe_executor prevents a specialist from running if a required
    artifact is missing from the state.

    The response uses ONLY scratchpad for routing signals - no messages pollution.
    Router reads scratchpad.recommended_specialists and injects dependency context
    into its prompt. This keeps internal orchestration out of user-visible stream.

    CRITICAL: The blocked specialist is added to forbidden_specialists so Router
    won't route back to it until the dependency is satisfied (ADR-CORE-016).
    """
    # Arrange
    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "artifact_requiring_specialist"
    mock_specialist.specialist_config = {
        "requires_artifacts": ["system_plan"],
        "artifact_providers": {"system_plan": "systems_architect"}
    }

    safe_executor = node_executor_instance.create_safe_executor(mock_specialist)
    initial_state = create_test_state(turn_count=1)

    # Act
    result = safe_executor(initial_state)

    # Assert
    mock_specialist.execute.assert_not_called()

    # Recommendation flows through scratchpad (not messages - no pollution)
    assert "scratchpad" in result
    assert result["scratchpad"]["recommended_specialists"] == ["systems_architect"]
    # ADR-CORE-016: Blocked specialist added to forbidden_specialists to prevent routing loops
    assert result["scratchpad"]["forbidden_specialists"] == ["artifact_requiring_specialist"]
    # No messages - internal orchestration stays out of user-visible stream
    assert "messages" not in result
    # Routing history still tracked for observability
    assert "routing_history" in result
    assert result["routing_history"] == ["artifact_requiring_specialist"]

def test_create_missing_artifact_response_format(node_executor_instance):
    """
    Tests the specific format of the missing artifact response.

    The response uses ONLY scratchpad - no messages pollution.
    This is intentional: Router reads scratchpad.recommended_specialists and builds
    its own dependency context. The internal "cannot execute" message should never
    appear in user-visible conversation.

    ADR-CORE-016: Blocked specialist is added to forbidden_specialists so Router
    won't route back to it until the dependency is satisfied.
    """
    # Act
    response = node_executor_instance.create_missing_artifact_response(
        specialist_name="test_specialist",
        missing_artifacts=["artifact1"],
        recommended_specialists=["provider_specialist"]
    )
    # Assert: recommendation in scratchpad
    assert response["scratchpad"]["recommended_specialists"] == ["provider_specialist"]
    # Assert: blocked specialist in forbidden_specialists (prevents routing loops)
    assert response["scratchpad"]["forbidden_specialists"] == ["test_specialist"]
    # Assert: NO messages pollution
    assert "messages" not in response
