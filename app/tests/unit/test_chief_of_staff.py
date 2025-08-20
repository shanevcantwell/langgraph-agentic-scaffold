# app/tests/unit/test_chief_of_staff.py

import unittest
from unittest.mock import MagicMock, patch
from app.src.workflow.chief_of_staff import ChiefOfStaff
from app.src.specialists.base import BaseSpecialist

class TestChiefOfStaff(unittest.TestCase):

    @patch("app.src.workflow.chief_of_staff.ConfigLoader")
    @patch("app.src.workflow.chief_of_staff.get_specialist_class")
    def test_load_specialists(self, mock_get_specialist_class, mock_config_loader):
        # Arrange
        mock_config = {
            "specialists": {
                "specialist1": {},
                "specialist2": {"type": "wrapped", "source": "/fake/path"}
            }
        }
        mock_config_loader.return_value.get_config.return_value = mock_config

        mock_specialist1 = MagicMock(spec=BaseSpecialist)
        mock_specialist2 = MagicMock(spec=BaseSpecialist)
        mock_get_specialist_class.side_effect = [mock_specialist1, mock_specialist2]

        # Act
        chief_of_staff = ChiefOfStaff()

        # Assert
        self.assertEqual(len(chief_of_staff.specialists), 2)
        self.assertIn("specialist1", chief_of_staff.specialists)
        self.assertIn("specialist2", chief_of_staff.specialists)
        mock_get_specialist_class.assert_any_call("specialist1", {})
        mock_get_specialist_class.assert_any_call("specialist2", {"type": "wrapped", "source": "/fake/path"})

    @patch("app.src.workflow.chief_of_staff.ConfigLoader")
    def test_compile_graph(self, mock_config_loader):
        # Arrange
        mock_config = {
            "specialists": {
                "router_specialist": {},
                "specialist1": {}
            }
        }
        mock_config_loader.return_value.get_config.return_value = mock_config

        chief_of_staff = ChiefOfStaff()
        chief_of_staff.specialists["router_specialist"] = MagicMock()
        chief_of_staff.specialists["specialist1"] = MagicMock()

        # Act
        graph = chief_of_staff.compile_graph()

        # Assert
        self.assertIsNotNone(graph)
        self.assertIn("router_specialist", graph.nodes)
        self.assertIn("specialist1", graph.nodes)

if __name__ == '__main__':
    unittest.main()
