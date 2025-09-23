# app/tests/unit/test_graph_builder.py

from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from langgraph.pregel import Pregel

from app.src.workflow.graph_builder import GraphBuilder
from app.src.specialists.base import BaseSpecialist

@patch("app.src.workflow.graph_builder.AdapterFactory")
@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
@patch("app.src.workflow.graph_builder.ConfigLoader")
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
    builder = GraphBuilder()

    # --- Assert ---
    # Check that all specialists were loaded
    assert len(builder.specialists) == 3
    assert "router_specialist" in builder.specialists
    assert "specialist1" in builder.specialists
    assert "specialist2" in builder.specialists

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

@patch("app.src.workflow.graph_builder.AdapterFactory")
@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
@patch("app.src.workflow.graph_builder.ConfigLoader")
def test_build_graph(mock_config_loader, mock_get_specialist_class, mock_load_prompt, mock_adapter_factory):
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
    
    # Mock specialists to pass pre-flight checks
    for class_name in ["RouterSpecialist", "SomeOtherSpecialist"]:
        mock_class = MagicMock()
        mock_instance = MagicMock(spec=BaseSpecialist, is_enabled=True)
        mock_instance._perform_pre_flight_checks.return_value = True
        mock_class.return_value = mock_instance
        mock_get_specialist_class.side_effect = [mock_class] if mock_get_specialist_class.side_effect is None else mock_get_specialist_class.side_effect + [mock_class]

    # --- Act ---
    builder = GraphBuilder()
    graph = builder.build()

    # --- Assert ---
    assert graph is not None
    assert isinstance(graph, Pregel)
    assert "router_specialist" in graph.nodes
    assert "some_other_specialist" in graph.nodes