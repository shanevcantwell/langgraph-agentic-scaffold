# app/tests/unit/test_chief_of_staff.py

from langgraph.graph import StateGraph
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from src.workflow.chief_of_staff import ChiefOfStaff
from src.specialists.base import BaseSpecialist

@pytest.fixture
def chief_of_staff_instance(mocker):
    """Provides a mocked ChiefOfStaff instance for testing decision logic."""
    # We patch the __init__ method to prevent it from running its complex setup
    # logic (loading configs, building graphs), as we only want to test the
    # decision method in isolation for some tests.
    with patch.object(ChiefOfStaff, '__init__', lambda x: None):
        chief = ChiefOfStaff()
        # Mock any attributes needed by the method under test
        chief.specialists = {} 
        yield chief

def test_decide_next_specialist_normal_route(chief_of_staff_instance):
    """Tests that the function returns the correct specialist name from the state."""
    state = {"next_specialist": "file_specialist", "turn_count": 1}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == "file_specialist"

@patch("src.workflow.chief_of_staff.AdapterFactory")
@patch("src.workflow.chief_of_staff.get_specialist_class")
@patch("src.workflow.chief_of_staff.ConfigLoader")
def test_load_specialists_and_configure_router(mock_config_loader, mock_get_specialist_class, mock_adapter_factory):
    """
    Tests that specialists are loaded and that the router specialist is
    re-configured with a dynamic prompt (the "morning standup").
    """
    # --- Arrange ---
    mock_config = {
        "specialists": {
            "router_specialist": {"model": "gemini-test", "provider": "gemini", "prompt_file": "fake_router.md"},
            "specialist1": {"description": "Test specialist 1", "model": "gemini-test", "provider": "gemini", "prompt_file": "fake1.md"},
            "specialist2": {"description": "Test specialist 2", "model": "gemini-test", "provider": "gemini", "prompt_file": "fake2.md"}
        }
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

    # Check that the AdapterFactory was called to create a NEW adapter for the router
    # This is the key assertion for the "morning standup" logic.
    mock_factory_instance.create_adapter.assert_called_once()
    
    # Check the arguments of the call to create_adapter
    call_args, call_kwargs = mock_factory_instance.create_adapter.call_args
    assert call_kwargs['specialist_name'] == "router_specialist"
    dynamic_prompt = call_kwargs['system_prompt']
    assert isinstance(dynamic_prompt, str)
    assert "Test specialist 1" in dynamic_prompt
    assert "Test specialist 2" in dynamic_prompt

    # Check that the router's adapter was replaced with the new one
    assert chief_of_staff.specialists["router_specialist"].llm_adapter == mock_factory_instance.create_adapter.return_value

@patch("src.workflow.chief_of_staff.ConfigLoader")
@patch("src.workflow.chief_of_staff.get_specialist_class")
def test_get_graph(mock_get_specialist_class, mock_config_loader):
    """Tests that a valid graph is built and returned with all nodes."""
    # --- Arrange ---
    mock_config = {
        "specialists": {
            "router_specialist": {"prompt_file": "fake.md"},
            "some_other_specialist": {"description": "desc"}
        }
    }
    mock_config_loader.return_value.get_config.return_value = mock_config
    
    mock_router_class = MagicMock()
    mock_other_class = MagicMock()
    mock_get_specialist_class.side_effect = [mock_router_class, mock_other_class]
    
    mock_router_instance = MagicMock(spec=BaseSpecialist)
    mock_other_instance = MagicMock(spec=BaseSpecialist)
    mock_router_class.return_value = mock_router_instance
    mock_other_class.return_value = mock_other_instance

    # --- Act ---
    chief_of_staff = ChiefOfStaff()
    graph = chief_of_staff.get_graph()

    # --- Assert ---
    assert graph is not None
    assert isinstance(graph, StateGraph)
    assert "router_specialist" in graph.nodes
    assert "some_other_specialist" in graph.nodes

def test_decide_next_specialist_handles_error(chief_of_staff_instance):
    """Tests that the function routes to END when an error is present in the state."""
    state = {"error": "A critical error occurred", "turn_count": 1}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == END

def test_decide_next_specialist_handles_max_turns(chief_of_staff_instance):
    """Tests that the function routes to END when the max turn count is reached."""
    state = {"turn_count": 10, "next_specialist": "file_specialist"}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == END

def test_decide_next_specialist_handles_no_route(chief_of_staff_instance):
    """Tests that the function routes to END if the router fails to provide a next step."""
    state = {"next_specialist": None, "turn_count": 1}
    result = chief_of_staff_instance.decide_next_specialist(state)
    assert result == END
