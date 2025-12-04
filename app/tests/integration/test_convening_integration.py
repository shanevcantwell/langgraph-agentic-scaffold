import pytest
from unittest.mock import MagicMock, patch
from app.src.workflow.graph_builder import GraphBuilder
from app.src.enums import CoreSpecialist
from app.src.graph.state import GraphState

class TestConveningIntegration:
    
    @pytest.fixture
    def convening_config(self):
        return {
            "architecture": "convening",
            "llm_providers": {},
            "specialists": {
                "router_specialist": {"type": "llm"},
                "triage_architect": {"type": "llm"},
                "facilitator_specialist": {"type": "llm"},
                "progenitor_alpha_specialist": {"type": "llm"},
                "progenitor_bravo_specialist": {"type": "llm"},
                "tribe_conductor": {"type": "llm"} # Explicitly defined or auto-created
            }
        }

    @patch("app.src.workflow.graph_builder.ConfigLoader")
    @patch("app.src.workflow.graph_builder.AdapterFactory")
    @patch("app.src.workflow.graph_builder.NodeExecutor")
    @patch("app.src.workflow.graph_builder.GraphBuilder._load_and_configure_specialists")
    def test_graph_builder_wires_convening_architecture(
        self, 
        mock_load_specialists, 
        mock_executor, 
        mock_factory, 
        mock_loader,
        convening_config
    ):
        # Setup mocks
        mock_loader.return_value.get_config.return_value = convening_config
        
        # Mock specialists
        mock_conductor = MagicMock()
        mock_conductor.agent_router.mapping = {"default": "progenitor_bravo_specialist"}
        
        mock_specialists = {
            "router_specialist": MagicMock(),
            "tribe_conductor": mock_conductor,
            "progenitor_bravo_specialist": MagicMock(),
            "triage_architect": MagicMock()
        }
        mock_load_specialists.return_value = mock_specialists
        
        # Initialize Builder
        builder = GraphBuilder()
        
        # Build Graph
        graph = builder.build()
        
        # Verify Entry Point
        # LangGraph compiled graph doesn't expose entry point easily, 
        # but we can check if the method was called.
        # Actually, we can check the internal graph structure if we access the underlying graph.
        
        # But simpler: Verify _build_convening_graph was called
        # We can't easily spy on self method without more complex mocking.
        
        # Let's verify the graph has the expected nodes.
        # compiled_graph.get_graph().nodes
        nodes = graph.get_graph().nodes
        assert "tribe_conductor" in nodes
        assert "progenitor_bravo_specialist" in nodes
        assert "router_specialist" not in nodes # Should be excluded from nodes list in convening graph
        
        # Verify Edges
        # We can't easily inspect edges on compiled graph without traversing.
        # But if it compiled without error, that's a good sign.

    @patch("app.src.workflow.graph_builder.ConfigLoader")
    @patch("app.src.workflow.graph_builder.AdapterFactory")
    @patch("app.src.workflow.graph_builder.NodeExecutor")
    @patch("app.src.workflow.graph_builder.GraphBuilder._load_and_configure_specialists")
    def test_default_architecture_fallback(
        self, 
        mock_load_specialists, 
        mock_executor, 
        mock_factory, 
        mock_loader
    ):
        # Config without architecture flag
        config = {"specialists": {"router_specialist": MagicMock()}}
        mock_loader.return_value.get_config.return_value = config
        mock_load_specialists.return_value = config["specialists"]
        
        builder = GraphBuilder()
        graph = builder.build()
        
        nodes = graph.get_graph().nodes
        assert "router_specialist" in nodes
