# app/tests/unit/test_chief_of_staff.py

from langgraph.graph import StateGraph
import unittest
from unittest.mock import MagicMock, patch
from app.src.workflow.chief_of_staff import ChiefOfStaff
from app.src.specialists.base import BaseSpecialist

class TestChiefOfStaff(unittest.TestCase):

    @patch("app.src.workflow.chief_of_staff.ConfigLoader")
    @patch("app.src.workflow.chief_of_staff.get_specialist_class")
    def test_load_specialists(self, mock_get_specialist_class, mock_config_loader):
        """Tests that specialists are loaded and the router is configured."""
        # --- Arrange ---
        mock_config = {
            "specialists": {
                "router_specialist": {"prompt_file": "fake.md"},
                "specialist1": {"description": "Test specialist 1"}
            }
        }
        mock_config_loader.return_value.get_config.return_value = mock_config

        # Mock the specialist classes and their instances
        mock_router_class = MagicMock()
        mock_specialist1_class = MagicMock()
        mock_get_specialist_class.side_effect = [mock_router_class, mock_specialist1_class]

        mock_router_instance = MagicMock(spec=BaseSpecialist)
        mock_specialist1_instance = MagicMock(spec=BaseSpecialist)
        mock_router_class.return_value = mock_router_instance
        mock_specialist1_class.return_value = mock_specialist1_instance

        # --- Act ---
        chief_of_staff = ChiefOfStaff()

        # --- Assert ---
        # Check that specialists were loaded
        self.assertEqual(len(chief_of_staff.specialists), 2)
        self.assertIn("specialist1", chief_of_staff.specialists)
        self.assertIn("router_specialist", chief_of_staff.specialists)
        
        # Check that the router's adapter was re-configured (the core of the "morning standup")
        # We assert that the llm_adapter attribute of the router instance was set.
        # In a real test, we might mock AdapterFactory to check it was called with the right prompt.
        self.assertIsNotNone(mock_router_instance.llm_adapter)

    @patch("app.src.workflow.chief_of_staff.ConfigLoader")
    @patch("app.src.workflow.chief_of_staff.get_specialist_class")
    @patch("app.src.workflow.chief_of_staff.AdapterFactory")
    def test_get_graph(self, mock_adapter_factory, mock_get_specialist_class, mock_config_loader):
        """Tests that a valid graph is built and returned."""
        # --- Act ---
        # We can use a minimal config for this test, as we're mocking the instantiation
        mock_config_loader.return_value.get_config.return_value = {"specialists": {"router_specialist": {}}}
        chief_of_staff = ChiefOfStaff()
        graph = chief_of_staff.get_graph()

        # --- Assert ---
        self.assertIsNotNone(graph)
        self.assertIsInstance(graph, StateGraph)
        self.assertIn("router", graph.nodes)

if __name__ == '__main__':
    unittest.main()
