# app/tests/unit/test_wrapped_specialist.py

import unittest
from unittest.mock import MagicMock, patch
from app.src.specialists.open_swe_specialist import OpenSweSpecialist

class TestWrappedSpecialist(unittest.TestCase):

    @patch("importlib.util.spec_from_file_location")
    @patch("importlib.util.module_from_spec")
    def test_load_external_agent(self, mock_module_from_spec, mock_spec_from_file_location):
        # Arrange
        mock_spec = MagicMock()
        mock_spec_from_file_location.return_value = mock_spec

        mock_module = MagicMock()
        mock_module.Agent = MagicMock()
        mock_module_from_spec.return_value = mock_module

        # Act
        specialist = OpenSweSpecialist(specialist_name="open_swe_specialist", source="/fake/path/to/agent.py")

        # Assert
        mock_spec_from_file_location.assert_called_with("external_agent", "/fake/path/to/agent.py")
        mock_module_from_spec.assert_called_with(mock_spec)
        mock_spec.loader.exec_module.assert_called_with(mock_module)
        self.assertIsNotNone(specialist.external_agent)

    def test_execute(self):
        # Arrange
        specialist = OpenSweSpecialist(specialist_name="open_swe_specialist", source="/fake/path/to/agent.py")
        specialist.external_agent = MagicMock()
        specialist.external_agent.run.return_value = "Hello from the wrapped agent!"

        initial_state = {
            "messages": [{"role": "user", "content": "Hello"}]
        }

        # Act
        result_state = specialist.execute(initial_state)

        # Assert
        self.assertEqual(len(result_state["messages"]), 2)
        self.assertEqual(result_state["messages"][-1].content, "Hello from the wrapped agent!")

if __name__ == '__main__':
    unittest.main()
