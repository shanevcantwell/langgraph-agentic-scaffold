# app/tests/unit/test_config_loader.py

import unittest
from unittest.mock import patch, mock_open
from src.utils.config_loader import ConfigLoader

class TestConfigLoader(unittest.TestCase):

    @patch("builtins.open", new_callable=mock_open, read_data="specialists:\n  my_specialist:\n    model: gemini-1.5-flash")
    def test_load_config(self, mock_file):
        # Arrange
        # Clear the singleton instance to ensure a fresh load
        ConfigLoader._instance = None
        ConfigLoader._config = None

        # Act
        config = ConfigLoader().get_config()

        # Assert
        self.assertIn("specialists", config)
        self.assertIn("my_specialist", config["specialists"])
        self.assertEqual(config["specialists"]["my_specialist"]["model"], "gemini-1.5-flash")

if __name__ == '__main__':
    unittest.main()
