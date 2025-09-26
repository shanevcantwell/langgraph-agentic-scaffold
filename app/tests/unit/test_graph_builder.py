# app/tests/unit/test_graph_builder.py
from unittest.mock import MagicMock, patch, PropertyMock
import pytest
from langgraph.pregel import Pregel

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.errors import SpecialistLoadError
from app.src.specialists.base import BaseSpecialist

def create_mock_specialist(name, config, is_enabled=True, pre_flight_passes=True):
    """Helper function to create a configured mock specialist instance."""
    instance = MagicMock(spec=BaseSpecialist, specialist_name=name, specialist_config=config)
    # Use PropertyMock for properties like is_enabled
    type(instance).is_enabled = PropertyMock(return_value=is_enabled)
    # Mock the pre-flight check method
    instance._perform_pre_flight_checks.return_value = pre_flight_passes
    # Return a mock class that returns this instance
    return MagicMock(return_value=instance)

# (ADR-TS-001, Task 2.1) Refactored to use centralized fixtures.

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
def test_load_specialists_and_configure_router(
    mock_get_specialist_class,
    mock_load_prompt,
    mock_config_loader, 
    mock_adapter_factory
):
    """
    Tests that specialists are loaded and that the router specialist is
    re-configured with a dynamic prompt.
    """
    # --- Arrange ---
    specialist_configs = {
        "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake_router.md"},
        "specialist1": {"type": "llm", "description": "Test specialist 1", "llm_config": "gemini-test", "prompt_file": "fake1.md"},
        "specialist2": {"type": "llm", "description": "Test specialist 2", "llm_config": "gemini-test", "prompt_file": "fake2.md"},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = specialist_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model", "api_key": "test_key"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    def get_class_side_effect(name, config):
        return create_mock_specialist(name, config)

    mock_get_specialist_class.side_effect = get_class_side_effect

    # --- Act ---
    with patch.object(GraphBuilder, '_configure_router') as mock_configure_router:
        builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)

        # --- Assert ---
        mock_configure_router.assert_called_once()

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
def test_build_graph(
    mock_get_specialist_class,
    mock_load_prompt,
    mock_config_loader,
    mock_adapter_factory
):
    """Tests that a valid graph is built and returned with all nodes."""
    # --- Arrange ---
    spec_configs = {
        "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake.md"},
        "some_other_specialist": {"type": "procedural", "description": "desc"},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model", "api_key": "test_key"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    def get_class_side_effect(name, config):
        return create_mock_specialist(name, config)

    mock_get_specialist_class.side_effect = get_class_side_effect

    # --- Act ---
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()

    # --- Assert ---
    assert graph is not None
    assert isinstance(graph, Pregel)
    assert "router_specialist" in graph.nodes
    assert "some_other_specialist" in graph.nodes

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
def test_graph_builder_handles_disabled_specialist(mock_get_specialist_class, mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Tests that a specialist with is_enabled=False is not added to the graph."""
    # Arrange
    spec_configs = {
        "router_specialist": {"type": "procedural", "prompt_file": "fake.md", "llm_config": "gemini-test"},
        "enabled_specialist": {"type": "procedural"},
        "disabled_specialist": {"type": "procedural", "is_enabled": False},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model", "api_key": "test_key"}}
    mock_config['workflow'] = {"entry_point": "enabled_specialist"}

    def get_class_side_effect(name, config):
        is_enabled = config.get("is_enabled", True)
        return create_mock_specialist(name, config, is_enabled=is_enabled)

    mock_get_specialist_class.side_effect = get_class_side_effect

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()

    # Assert
    assert "enabled_specialist" in graph.nodes
    assert "disabled_specialist" not in graph.nodes

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
@patch("app.src.workflow.graph_builder.get_specialist_class")
def test_graph_builder_handles_pre_flight_check_failure(mock_get_specialist_class, mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Tests that a specialist failing pre-flight checks is not added."""
    # Arrange
    spec_configs = {
        "router_specialist": {"type": "procedural", "prompt_file": "fake.md", "llm_config": "gemini-test"},
        "passing_specialist": {"type": "procedural"},
        "failing_specialist": {"type": "procedural"},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model", "api_key": "test_key"}}
    mock_config['workflow'] = {"entry_point": "passing_specialist"}

    def get_class_side_effect(name, config):
        pre_flight_passes = name != "failing_specialist"
        return create_mock_specialist(name, config, pre_flight_passes=pre_flight_passes)

    mock_get_specialist_class.side_effect = get_class_side_effect

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()

    # Assert
    assert "passing_specialist" in graph.nodes
    assert "failing_specialist" not in graph.nodes

def test_graph_builder_raises_error_on_invalid_entry_point(mock_config_loader, mock_adapter_factory):
    """Tests that an error is raised if the entry point is not a valid specialist."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"real_specialist": {"type": "procedural"}}
    mock_config['workflow'] = {"entry_point": "fake_specialist"}

    # Act & Assert
    with pytest.raises(ValueError, match="Found edge starting at unknown node 'router_specialist'"):
        with patch("app.src.workflow.graph_builder.get_specialist_class"):
             GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory).build()

@patch("app.src.workflow.graph_builder.get_specialist_class", side_effect=ImportError("Module not found"))
def test_graph_builder_raises_error_on_get_specialist_class_failure(mock_get_specialist, mock_config_loader, mock_adapter_factory):
    """Tests that a SpecialistLoadError is raised if a specialist class cannot be imported."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"bad_specialist": {"type": "procedural"}}

    # Act & Assert
    with pytest.raises(SpecialistLoadError, match="Could not load specialist 'bad_specialist'"):
        GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)

@patch("app.src.workflow.graph_builder.load_prompt", side_effect=IOError("File not found"))
def test_graph_builder_raises_error_on_load_prompt_failure(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Tests that a SpecialistLoadError is raised if a prompt file cannot be loaded."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"prompt_specialist": {"type": "llm", "llm_config": "test", "prompt_file": "bad.md"}}

    # Act & Assert
    with pytest.raises(SpecialistLoadError, match="Could not load specialist 'prompt_specialist'"):
        with patch("app.src.workflow.graph_builder.get_specialist_class"):
            GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)