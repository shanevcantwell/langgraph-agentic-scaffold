# app/tests/unit/test_chief_of_staff.py

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel

from app.src.workflow.chief_of_staff import ChiefOfStaff
from app.src.specialists.base import BaseSpecialist

@pytest.fixture
def chief_of_staff_instance(mocker):
    """Provides a mocked ChiefOfStaff instance for testing decision logic."""
    # We patch the __init__ method to prevent it from running its complex setup
    # logic (loading configs, building graphs), as we only want to test the
    # decision method in isolation for some tests.
    with patch.object(ChiefOfStaff, '__init__', lambda x: None):
        chief = ChiefOfStaff()
        # Mock any attributes needed by the method under test
        chief.max_loop_cycles = 3
        chief.min_loop_len = 1
        chief.specialists = {} 
        yield chief

def test_decide_next_specialist_normal_route(chief_of_staff_instance):
    """Tests that the function returns the correct specialist name from the state."""
    state = {"next_specialist": "file_specialist", "turn_count": 1}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == "file_specialist"

@patch("app.src.workflow.chief_of_staff.AdapterFactory")
@patch("app.src.workflow.chief_of_staff.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.chief_of_staff.get_specialist_class")
@patch("app.src.workflow.chief_of_staff.ConfigLoader")
def test_load_specialists_and_configure_router(mock_config_loader, mock_get_specialist_class, mock_load_prompt, mock_adapter_factory):
    """
    Tests that specialists are loaded and that the router specialist is
    re-configured with a dynamic prompt (the "morning standup").
    """
    # --- Arrange ---
    mock_config = {
        "llm_providers": {
            "gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}
        },
        "specialists": {
            "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake_router.md"},
            "specialist1": {"type": "llm", "description": "Test specialist 1", "llm_config": "gemini-test", "prompt_file": "fake1.md"},
            "specialist2": {"type": "llm", "description": "Test specialist 2", "llm_config": "gemini-test", "prompt_file": "fake2.md"}
        },
        "workflow": {"entry_point": "router_specialist"}
    }
    mock_config_loader.return_value.get_config.return_value = mock_config

    # Mock the specialist classes and their instances
    mock_router_class = MagicMock()
    mock_specialist1_class = MagicMock()
    mock_specialist2_class = MagicMock()
    mock_get_specialist_class.side_effect = [mock_router_class, mock_specialist1_class, mock_specialist2_class]

    mock_router_instance = MagicMock(spec=BaseSpecialist)
    mock_specialist1_instance = MagicMock(spec=BaseSpecialist)
    mock_specialist2_instance = MagicMock(spec=BaseSpecialist)
    
    # Set the 'is_enabled' property to True for the mock instances
    type(mock_router_instance).is_enabled = PropertyMock(return_value=True)
    type(mock_specialist1_instance).is_enabled = PropertyMock(return_value=True)
    type(mock_specialist2_instance).is_enabled = PropertyMock(return_value=True)
    
    # Make sure pre-flight checks pass
    mock_router_instance._perform_pre_flight_checks.return_value = True
    mock_specialist1_instance._perform_pre_flight_checks.return_value = True
    mock_specialist2_instance._perform_pre_flight_checks.return_value = True

    mock_router_class.return_value = mock_router_instance
    mock_specialist1_class.return_value = mock_specialist1_instance
    mock_specialist2_class.return_value = mock_specialist2_instance

    # --- Act ---
    chief_of_staff = ChiefOfStaff()

    # --- Assert ---
    # Check that all specialists were loaded
    assert len(chief_of_staff.specialists) == 3
    assert "router_specialist" in chief_of_staff.specialists
    assert "specialist1" in chief_of_staff.specialists
    assert "specialist2" in chief_of_staff.specialists

    # Get the mock instance that was created when AdapterFactory() was called
    mock_factory_instance = mock_adapter_factory.return_value

    # It's called for specialist1, specialist2, and then the router.
    assert mock_factory_instance.create_adapter.call_count >= 1

    # Find the call for the router specifically
    router_call_args = None
    for call in mock_factory_instance.create_adapter.call_args_list:
        # The router's dynamic prompt will contain the descriptions of other specialists
        if 'Test specialist 1' in call.kwargs.get('system_prompt', ''):
            router_call_args = call.kwargs
            break
    
    assert router_call_args is not None, "AdapterFactory was not called to configure the router with a dynamic prompt."
    dynamic_prompt = router_call_args['system_prompt']
    assert isinstance(dynamic_prompt, str)
    assert "Test specialist 1" in dynamic_prompt
    assert "Test specialist 2" in dynamic_prompt

@patch("app.src.workflow.chief_of_staff.AdapterFactory")
@patch("app.src.workflow.chief_of_staff.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.chief_of_staff.get_specialist_class")
@patch("app.src.workflow.chief_of_staff.ConfigLoader")
def test_get_graph(mock_config_loader, mock_get_specialist_class, mock_load_prompt, mock_adapter_factory):
    """Tests that a valid graph is built and returned with all nodes."""
    # --- Arrange ---
    mock_config = {
        "llm_providers": {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}},
        "specialists": {
            "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake.md"},
            "some_other_specialist": {"type": "procedural", "description": "desc"}
        },
        "workflow": {"entry_point": "router_specialist"}
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    mock_router_class = MagicMock()
    mock_other_class = MagicMock()
    mock_get_specialist_class.side_effect = [mock_router_class, mock_other_class]
    
    mock_router_instance = MagicMock(spec=BaseSpecialist)
    mock_other_instance = MagicMock(spec=BaseSpecialist)
    type(mock_router_instance).is_enabled = PropertyMock(return_value=True)
    type(mock_other_instance).is_enabled = PropertyMock(return_value=True)
    mock_router_instance._perform_pre_flight_checks.return_value = True
    mock_other_instance._perform_pre_flight_checks.return_value = True
    mock_router_instance.specialist_name = "router_specialist"
    mock_other_instance.specialist_name = "some_other_specialist"
    mock_router_class.return_value = mock_router_instance
    mock_other_class.return_value = mock_other_instance

    # --- Act ---
    chief_of_staff = ChiefOfStaff()
    graph = chief_of_staff.get_graph()

    # --- Assert ---
    assert graph is not None
    # The compiled graph is a 'Pregel' object, not a 'StateGraph'
    assert isinstance(graph, Pregel)
    assert "router_specialist" in graph.nodes
    assert "some_other_specialist" in graph.nodes

def test_decide_next_specialist_detects_loop(chief_of_staff_instance):
    """Tests that the function routes to END when a repeating loop is detected."""
    # Configure the instance for the test
    chief_of_staff_instance.max_loop_cycles = 3
    chief_of_staff_instance.min_loop_len = 2

    # This history represents a loop of ['A', 'B'] repeating 3 times.
    state = {
        "routing_history": ["C", "A", "B", "A", "B", "A", "B"],
        "next_specialist": "some_specialist"
    }
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == END

def test_decide_next_specialist_allows_non_loop(chief_of_staff_instance):
    """Tests that the function does not halt for a non-looping history."""
    chief_of_staff_instance.max_loop_cycles = 2
    chief_of_staff_instance.min_loop_len = 2

    state = {
        "routing_history": ["A", "B", "C", "D"],
        "next_specialist": "some_specialist"
    }
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == "some_specialist"

def test_decide_next_specialist_handles_no_route(chief_of_staff_instance):
    """Tests that the function routes to END if the router fails to provide a next step."""
    state = {"next_specialist": None, "turn_count": 1}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == END
