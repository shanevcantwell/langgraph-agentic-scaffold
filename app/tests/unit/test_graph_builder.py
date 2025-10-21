# app/tests/unit/test_graph_builder.py
from unittest.mock import MagicMock, patch, PropertyMock, ANY
import pytest
from langgraph.pregel import Pregel

from app.src.workflow.graph_builder import GraphBuilder
from app.src.utils.errors import SpecialistLoadError, WorkflowError
from app.src.specialists.base import BaseSpecialist
from app.src.specialists import * # Import all real specialist classes

# (ADR-TS-001, Task 2.1) Refactored to use centralized fixtures.

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_load_and_configure_specialists(
    mock_load_prompt,
    mock_config_loader, 
    mock_adapter_factory
):
    """
    Tests that specialists are loaded and that the router specialist is
    re-configured with a dynamic prompt.
    """
    # --- Arrange ---
    # We use real specialist classes now, so the config needs to be more realistic.
    specialist_configs = {
        "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake_router.md", "description": "d"},
        "prompt_triage_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake_triage.md", "description": "d"},
        "file_specialist": {"type": "procedural", "description": "File ops"},
        "end_specialist": {"type": "procedural"},
        "response_synthesizer_specialist": {"type": "llm", "llm_config": "gemini-test"},
        "archiver_specialist": {"type": "procedural"},
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = specialist_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # --- Act ---
    # We no longer need to mock get_specialist_class, we use the real ones.
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    
    # --- Assert ---
    # 1. Check that specialists were loaded
    assert "router_specialist" in builder.specialists
    assert "prompt_triage_specialist" in builder.specialists
    assert "end_specialist" in builder.specialists
    assert "file_specialist" in builder.specialists
    
    # 2. Check that adapters were attached correctly
    mock_adapter_factory.create_adapter.assert_any_call("router_specialist", ANY)
    mock_adapter_factory.create_adapter.assert_any_call("prompt_triage_specialist", ANY)
    assert builder.specialists["end_specialist"].synthesizer.llm_adapter is not None

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_build_graph(
    mock_load_prompt,
    mock_config_loader,
    mock_adapter_factory
):
    """Tests that a valid graph is built and returned with all nodes."""
    # --- Arrange ---
    spec_configs = {
        "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "fake.md"},
        "file_specialist": {"type": "procedural", "description": "desc"},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # --- Act ---
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()

    # --- Assert ---
    assert graph is not None
    assert isinstance(graph, Pregel)
    assert "router_specialist" in graph.nodes
    assert "file_specialist" in graph.nodes

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_graph_builder_handles_disabled_specialist(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Tests that a specialist with is_enabled=False is not added to the graph."""
    # Arrange
    # We need a router for the graph to build correctly.
    spec_configs = {
        "router_specialist": {"type": "llm", "prompt_file": "fake.md", "llm_config": "gemini-test"},
        "file_specialist": {"type": "procedural", "description": "File ops"},
        "prompt_specialist": {"type": "llm", "llm_config": "gemini-test", "is_enabled": False, "description": "d"},
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()

    # Assert
    assert "router_specialist" in graph.nodes
    assert "file_specialist" in graph.nodes
    assert "prompt_specialist" not in graph.nodes

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_graph_builder_handles_pre_flight_check_failure(mock_load_prompt, mock_config_loader, mock_adapter_factory, mocker):
    """Tests that a specialist failing pre-flight checks is not added."""
    # Arrange
    # We need a router for the graph to build correctly.
    # We use real specialists and make one of them "fail" the check.
    spec_configs = {
        "router_specialist": {"type": "llm", "prompt_file": "fake.md", "llm_config": "gemini-test"},
        "file_specialist": {"type": "procedural"}, # This will pass
        "prompt_specialist": {"type": "llm", "llm_config": "gemini-test"}, # This will fail
        "end_specialist": {"type": "procedural"}
    }
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = spec_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}}
    mock_config['workflow'] = {"entry_point": "router_specialist"}
 
    # Patch the pre-flight check on the specific specialist class we want to fail.
    # This prevents the mock from incorrectly affecting other specialists like the router.
    mocker.patch('app.src.specialists.prompt_specialist.PromptSpecialist._perform_pre_flight_checks', return_value=False)
 
    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    graph = builder.build()
 
    # Assert
    assert "router_specialist" in graph.nodes
    assert "file_specialist" in graph.nodes # This one should pass the check
    assert "prompt_specialist" not in graph.nodes

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_graph_builder_defaults_on_invalid_entry_point(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Tests that the entry point defaults to router if the configured one is invalid."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"router_specialist": {"type": "llm", "llm_config": "test"}}
    mock_config['workflow'] = {"entry_point": "fake_specialist"}

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    # Assert
    assert builder.entry_point == "router_specialist"

@patch("app.src.workflow.graph_builder.get_specialist_class", side_effect=ImportError("Module not found"))
def test_graph_builder_raises_error_on_get_specialist_class_failure(mock_get_specialist, mock_config_loader, mock_adapter_factory):
    """Tests that a SpecialistLoadError is raised if a specialist class cannot be imported."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"bad_specialist": {"type": "procedural"}}

    # Act & Assert
    with pytest.raises(SpecialistLoadError, match="Could not load specialist 'bad_specialist'"):
        GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)

def test_graph_builder_raises_error_on_load_prompt_failure(mock_config_loader, mock_adapter_factory):
    """Tests that a SpecialistLoadError is raised if a prompt file cannot be loaded."""
    # Arrange
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {"router_specialist": {"type": "llm", "llm_config": "test", "prompt_file": "bad.md"}}
    mock_config['llm_providers'] = {"test": {"type": "gemini", "api_identifier": "test-model"}}

    # We patch load_prompt to simulate a file not being found.
    with patch("app.src.workflow.graph_builder.load_prompt", side_effect=IOError("File not found")):
        # Act & Assert
        with pytest.raises(SpecialistLoadError, match="Could not load specialist 'router_specialist'"):
            GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_safe_edges_raises_workflow_error_on_invalid_dest(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Test that _add_safe_conditional_edges raises WorkflowError for an invalid destination."""
    # Arrange
    mock_workflow = MagicMock()
    mock_decider = MagicMock(return_value="invalid_destination")
    destination_map = {"valid_dest": "valid_dest", "another_valid": "another_valid"}

    # Act & Assert
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    with pytest.raises(WorkflowError) as exc_info:
        builder._add_safe_conditional_edges(mock_workflow, "source_node", mock_decider, destination_map)

    # Verify the error message contains the expected information
    assert "Routing error from 'source_node'" in str(exc_info.value)
    assert "invalid_destination" in str(exc_info.value)
    assert "valid_dest" in str(exc_info.value)
    assert "another_valid" in str(exc_info.value)

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_router(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Test that the router edge uses the safe wrapper method."""
    # Arrange
    mock_workflow = MagicMock()
    mock_decider = MagicMock()
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {
        "router_specialist": {"type": "llm", "llm_config": "test"},
        "file_specialist": {"type": "procedural"}
    }
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    builder._wire_hub_and_spoke_edges(mock_workflow)

    # Assert
    # The call to add_conditional_edges should have been made with the safe_decider function
    # from _add_safe_conditional_edges, which is a wrapper around the actual decider.
    # We check that the `add_conditional_edges` method was called with the correct source and map.
    mock_workflow.add_conditional_edges.assert_called_once()
    call_args, _ = mock_workflow.add_conditional_edges.call_args
    assert call_args[0] == "router_specialist"
    assert call_args[2] == {"file_specialist": "file_specialist", "router_specialist": "router_specialist"}

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_critic(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Test that the critic edge uses the safe wrapper method."""
    # Arrange
    mock_workflow = MagicMock()
    mock_decider = MagicMock()
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {
        "router_specialist": {"type": "llm", "llm_config": "test"},
        "critic_specialist": {"type": "llm", "llm_config": "test", "revision_target": "router_specialist"}
    }
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    builder._wire_hub_and_spoke_edges(mock_workflow)

    # Assert
    # The call to add_conditional_edges should have been made with the safe_decider function
    # from _add_safe_conditional_edges, which is a wrapper around the actual decider.
    # We check that the `add_conditional_edges` method was called with the correct source and map.
    mock_workflow.add_conditional_edges.assert_called_once()
    call_args, _ = mock_workflow.add_conditional_edges.call_args
    assert call_args[0] == "critic_specialist"
    assert call_args[2] == {
        "router_specialist": "router_specialist",
        "end_specialist": "end_specialist",
        "critic_specialist": "critic_specialist"
    }

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_wire_hub_and_spoke_edges_uses_safe_wrapper_for_task_completion(mock_load_prompt, mock_config_loader, mock_adapter_factory):
    """Test that task completion edges use the safe wrapper method."""
    # Arrange
    mock_workflow = MagicMock()
    mock_decider = MagicMock()
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = {
        "router_specialist": {"type": "llm", "llm_config": "test"},
        "file_specialist": {"type": "procedural"}
    }
    mock_config['workflow'] = {"entry_point": "router_specialist"}

    # Act
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    builder._wire_hub_and_spoke_edges(mock_workflow)

    # Assert
    # The call to add_conditional_edges should have been made with the safe_decider function
    # from _add_safe_conditional_edges, which is a wrapper around the actual decider.
    # We check that the `add_conditional_edges` method was called with the correct source and map.
    mock_workflow.add_conditional_edges.assert_called_once()
    call_args, _ = mock_workflow.add_conditional_edges.call_args
    assert call_args[0] == "file_specialist"
    assert call_args[2] == {"end_specialist": "end_specialist", "router_specialist": "router_specialist"}