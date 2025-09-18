# app/tests/unit/test_chief_of_staff_governance.py

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from langgraph.graph import END

from app.src.workflow.chief_of_staff import ChiefOfStaff
from app.src.specialists.base import BaseSpecialist
from app.src.utils.errors import SpecialistError
from app.src.specialists.helpers import create_missing_artifact_response
from app.src.enums import CoreSpecialist

# Use a shared mock for the ConfigLoader across tests in this file
@pytest.fixture
def mock_config_loader(mocker):
    """Provides a mock for the ConfigLoader."""
    patcher = patch("app.src.workflow.chief_of_staff.ConfigLoader")
    mock_loader_class = patcher.start()
    mock_loader_instance = mock_loader_class.return_value
    yield mock_loader_instance
    patcher.stop()


def test_safe_executor_handles_specialist_exception(mock_config_loader):
    """
    Tests that the _create_safe_executor wrapper catches exceptions from a specialist
    and returns a state with a detailed error_report.
    """
    # Arrange
    mock_config_loader.get_config.return_value = {
        "specialists": {}, "workflow": {}
    }
    with patch("app.src.workflow.chief_of_staff.get_specialist_class"), \
         patch("app.src.workflow.chief_of_staff.load_prompt"), \
         patch("app.src.workflow.chief_of_staff.AdapterFactory"):
        chief = ChiefOfStaff()

    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "failing_specialist"
    mock_specialist.specialist_config = {}
    mock_specialist.execute.side_effect = SpecialistError("Something went wrong!")

    safe_executor = chief._create_safe_executor(mock_specialist)
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


def test_safe_executor_blocks_execution_on_missing_artifact(mock_config_loader):
    """
    Tests that the safe_executor prevents a specialist from running if a required
    artifact is missing from the state.
    """
    # Arrange
    mock_config_loader.get_config.return_value = {
        "specialists": {}, "workflow": {}
    }
    with patch("app.src.workflow.chief_of_staff.get_specialist_class"), \
         patch("app.src.workflow.chief_of_staff.load_prompt"), \
         patch("app.src.workflow.chief_of_staff.AdapterFactory"):
        chief = ChiefOfStaff()

    mock_specialist = MagicMock(spec=BaseSpecialist)
    mock_specialist.specialist_name = "artifact_requiring_specialist"
    mock_specialist.specialist_config = {
        "requires_artifacts": ["system_plan"],
        "artifact_providers": {"system_plan": "systems_architect"}
    }

    safe_executor = chief._create_safe_executor(mock_specialist)
    initial_state = {"messages": [], "turn_count": 1}

    # Act
    result = safe_executor(initial_state)

    # Assert
    mock_specialist.execute.assert_not_called()
    expected_response = create_missing_artifact_response(
        specialist_name="artifact_requiring_specialist",
        missing_artifacts=["system_plan"],
        recommended_specialists=["systems_architect"]
    )
    assert result == expected_response


@patch("app.src.workflow.chief_of_staff.get_specialist_class")
@patch("app.src.workflow.chief_of_staff.load_prompt", return_value="prompt")
@patch("app.src.workflow.chief_of_staff.AdapterFactory")
def test_specialist_loading_respects_enabled_flag_and_preflight_checks(mock_adapter_factory, mock_load_prompt, mock_get_specialist_class, mock_config_loader):
    """
    Tests that specialists are correctly filtered during loading based on the
    'enabled' flag and the result of '_perform_pre_flight_checks'.
    """
    # Arrange
    mock_config_loader.get_config.return_value = {
        "llm_providers": {"mock_provider": {"type": "gemini", "api_identifier": "mock-model"}},
        "specialists": {
            "router_specialist": {"type": "llm", "llm_config": "mock_provider", "description": "Router"},
            "enabled_specialist": {"type": "procedural", "description": "This one works"},
            "disabled_specialist": {"enabled": False, "type": "procedural", "description": "This is disabled"},
            "failed_preflight_specialist": {"type": "procedural", "description": "This fails checks"}
        },
        "workflow": {"entry_point": "router_specialist"}
    }

    mock_router_class, mock_enabled_class, mock_disabled_class, mock_failed_class = [MagicMock() for _ in range(4)]
    mock_get_specialist_class.side_effect = [mock_router_class, mock_enabled_class, mock_disabled_class, mock_failed_class]

    mock_router_instance, mock_enabled_instance, mock_disabled_instance, mock_failed_instance = [MagicMock(spec=BaseSpecialist) for _ in range(4)]
    
    type(mock_router_instance).is_enabled = PropertyMock(return_value=True)
    mock_router_instance._perform_pre_flight_checks.return_value = True
    mock_router_class.return_value = mock_router_instance

    type(mock_enabled_instance).is_enabled = PropertyMock(return_value=True)
    mock_enabled_instance._perform_pre_flight_checks.return_value = True
    mock_enabled_class.return_value = mock_enabled_instance

    type(mock_disabled_instance).is_enabled = PropertyMock(return_value=False)
    mock_disabled_class.return_value = mock_disabled_instance

    type(mock_failed_instance).is_enabled = PropertyMock(return_value=True)
    mock_failed_instance._perform_pre_flight_checks.return_value = False
    mock_failed_class.return_value = mock_failed_instance

    # Act
    chief = ChiefOfStaff()

    # Assert
    loaded_specialists = chief.specialists.keys()
    assert "router_specialist" in loaded_specialists
    assert "enabled_specialist" in loaded_specialists
    assert "disabled_specialist" not in loaded_specialists
    assert "failed_preflight_specialist" not in loaded_specialists
    assert len(loaded_specialists) == 2

    mock_factory_instance = mock_adapter_factory.return_value
    router_adapter_call = next(c for c in mock_factory_instance.create_adapter.call_args_list if "Router" in c.kwargs.get('system_prompt', ''))
    router_dynamic_prompt = router_adapter_call.kwargs['system_prompt']

    assert "This one works" in router_dynamic_prompt
    assert "This is disabled" not in router_dynamic_prompt
    assert "This fails checks" not in router_dynamic_prompt


@patch("app.src.workflow.chief_of_staff.get_specialist_class")
@patch("app.src.workflow.chief_of_staff.load_prompt", return_value="prompt")
@patch("app.src.workflow.chief_of_staff.AdapterFactory")
def test_entry_point_validation_falls_back_to_router(mock_adapter_factory, mock_load_prompt, mock_get_specialist_class, mock_config_loader):
    """
    Tests that if the configured entry_point specialist fails to load, the
    ChiefOfStaff safely falls back to the default router specialist.
    """
    # Arrange
    mock_config_loader.get_config.return_value = {
        "llm_providers": {"mock_provider": {"type": "gemini", "api_identifier": "mock-model"}},
        "specialists": {
            "router_specialist": {"type": "llm", "llm_config": "mock_provider", "description": "Router"},
            "bad_entry_point": {"type": "procedural", "description": "This will fail"}
        },
        "workflow": {"entry_point": "bad_entry_point"} # Configure the invalid entry point
    }

    mock_router_class, mock_bad_entry_class = MagicMock(), MagicMock()
    mock_get_specialist_class.side_effect = [mock_router_class, mock_bad_entry_class]

    mock_router_instance = MagicMock(spec=BaseSpecialist)
    type(mock_router_instance).is_enabled = PropertyMock(return_value=True)
    mock_router_instance._perform_pre_flight_checks.return_value = True
    mock_router_class.return_value = mock_router_instance

    mock_bad_entry_instance = MagicMock(spec=BaseSpecialist)
    type(mock_bad_entry_instance).is_enabled = PropertyMock(return_value=True)
    mock_bad_entry_instance._perform_pre_flight_checks.return_value = False # Fails to load
    mock_bad_entry_class.return_value = mock_bad_entry_instance

    # Act
    chief = ChiefOfStaff()

    # Assert
    assert "bad_entry_point" not in chief.specialists
    assert chief.entry_point == CoreSpecialist.ROUTER.value


def test_decide_next_specialist_bypasses_loop_detection_for_intentional_loops(mock_config_loader):
    """
    Tests that the generic loop detection is bypassed when an intentional loop,
    like the web_builder's refinement cycle, is in progress.
    """
    # Arrange
    # We only need to test the decision logic, so we can bypass the complex __init__
    with patch.object(ChiefOfStaff, '__init__', lambda x: None):
        chief = ChiefOfStaff()
    chief.max_loop_cycles = 2
    chief.min_loop_len = 2

    # This history would normally trigger loop detection ([A, B] repeats 2 times)
    state = {
        "routing_history": ["C", "A", "B", "A", "B"],
        "next_specialist": "some_specialist",
        "scratchpad": {
            "web_builder_iteration": 1  # This signals an intentional loop
        }
    }

    # Act
    result = chief.decide_next_specialist(state)

    # Assert
    # The function should not return END, but rather the next specialist
    assert result != END
    assert result == "some_specialist"
