import pytest
from unittest.mock import MagicMock, patch
from app.src.convening.agent_router import AgentRouter
from app.src.convening.semantic_firewall import SemanticFirewall
from app.src.specialists.tribe_conductor import TribeConductor
from app.src.specialists.schemas._manifest import AgentAffinity

class TestConveningWiring:
    
    def test_agent_router_defaults(self):
        router = AgentRouter()
        assert router.route(AgentAffinity.ARCHITECTURE) == "progenitor_alpha_specialist"
        assert router.route(AgentAffinity.IMPLEMENTATION) == "progenitor_bravo_specialist"
        assert router.route(AgentAffinity.DEFAULT) == "progenitor_bravo_specialist"
        
    def test_semantic_firewall_slop(self):
        firewall = SemanticFirewall()
        slop = "I cannot fulfill this request because I am an AI."
        assert firewall.sanitize_output(slop) is not None # Currently just logs, doesn't block
        # If we change logic to block, this test should update.
        
    def test_semantic_firewall_truncation(self):
        firewall = SemanticFirewall()
        long_input = "a" * 100
        sanitized = firewall.sanitize_input(long_input, max_length=50)
        assert len(sanitized) < 100
        assert "TRUNCATED" in sanitized

    @patch("app.src.specialists.tribe_conductor.ManifestManager")
    def test_tribe_conductor_init(self, mock_manager_cls):
        conductor = TribeConductor("conductor", {})
        assert conductor.agent_router is not None
        assert conductor.firewall is not None
        
    @patch("app.src.specialists.tribe_conductor.ManifestManager")
    def test_tribe_conductor_routing(self, mock_manager_cls):
        conductor = TribeConductor("conductor", {})
        
        # Mock state with active branch
        mock_manager = mock_manager_cls.return_value
        mock_branch = MagicMock()
        mock_branch.status = "active"
        mock_branch.affinity = AgentAffinity.ARCHITECTURE
        mock_branch.filepath = "test.md"
        mock_manager.manifest.branches = {"b1": mock_branch}
        mock_manager.project_root = MagicMock()
        
        # Mock dereference
        with patch.object(conductor, 'dereference_branch', return_value="Context"):
            state = {
                "manifest_path": "manifest.json",
                "active_branch_id": "b1"
            }
            
            result = conductor._execute_logic(state)
            
            assert result["scratchpad"]["next_specialist"] == "progenitor_alpha_specialist"
            assert result["scratchpad"]["loaded_context"] == "Context"
