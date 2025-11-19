
import pytest
from unittest.mock import MagicMock, patch, ANY
from app.src.workflow.graph_builder import GraphBuilder
from app.src.enums import CoreSpecialist

@patch("app.src.workflow.graph_builder.load_prompt", return_value="Base prompt")
def test_context_engineering_graph_wiring(
    mock_load_prompt,
    mock_config_loader,
    mock_adapter_factory
):
    """
    Tests that the Context Engineering subgraph is correctly wired:
    1. TriageArchitect and Facilitator are nodes.
    2. Researcher and Summarizer are NOT nodes (MCP only).
    3. TriageArchitect routes to Facilitator or Router.
    4. Facilitator routes to Router.
    """
    # --- Arrange ---
    specialist_configs = {
        "router_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "router.md"},
        "triage_architect": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "triage.md"},
        "facilitator_specialist": {"type": "procedural", "description": "Facilitator"},
        "researcher_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "researcher.md"},
        "summarizer_specialist": {"type": "llm", "llm_config": "gemini-test", "prompt_file": "summarizer.md"},
        "end_specialist": {"type": "procedural", "llm_config": "gemini-test", "synthesis_prompt_file": "end.md"},
    }
    
    mock_config = mock_config_loader.get_config.return_value
    mock_config['specialists'] = specialist_configs
    mock_config['llm_providers'] = {"gemini-test": {"type": "gemini", "api_identifier": "gemini-test-model"}}
    mock_config['workflow'] = {"entry_point": "triage_architect"}

    # --- Act ---
    builder = GraphBuilder(config_loader=mock_config_loader, adapter_factory=mock_adapter_factory)
    
    # Mock the workflow object to capture add_node and add_conditional_edges calls
    mock_workflow = MagicMock()
    builder._add_nodes_to_graph(mock_workflow)
    builder._wire_hub_and_spoke_edges(mock_workflow)

    # --- Assert ---
    
    # 1. Verify Nodes
    # Triage and Facilitator should be nodes
    mock_workflow.add_node.assert_any_call("triage_architect", ANY)
    mock_workflow.add_node.assert_any_call("facilitator_specialist", ANY)
    
    # Researcher and Summarizer should NOT be nodes (MCP only)
    # We check that add_node was NOT called with these names
    added_nodes = [call.args[0] for call in mock_workflow.add_node.call_args_list]
    assert "researcher_specialist" not in added_nodes
    assert "summarizer_specialist" not in added_nodes
    
    # 2. Verify Edges
    # Triage -> [Facilitator | Router]
    mock_workflow.add_conditional_edges.assert_any_call(
        "triage_architect",
        builder.orchestrator.check_triage_outcome,
        {
            "facilitator_specialist": "facilitator_specialist",
            "router_specialist": "router_specialist"
        }
    )
    
    # Facilitator -> Router (Direct edge)
    mock_workflow.add_edge.assert_any_call("facilitator_specialist", "router_specialist")
    
    # 3. Verify Exclusions from Hub-and-Spoke
    # Triage and Facilitator should NOT have the standard check_task_completion edge
    # We check all calls to add_conditional_edges with check_task_completion
    for call in mock_workflow.add_conditional_edges.call_args_list:
        source_node = call.args[0]
        condition = call.args[1]
        if condition == builder.orchestrator.check_task_completion:
            assert source_node != "triage_architect"
            assert source_node != "facilitator_specialist"

