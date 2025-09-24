# Audited on Sept 23, 2025
# This file tests the behavior of fixtures defined in conftest.py

import pytest
import os

def test_load_env_does_not_override_existing_vars(monkeypatch, tmp_path):
    """
    Tests that the load_env fixture in conftest.py does NOT override
    environment variables that are already set. This is the default and
    expected behavior of python-dotenv.
    """
    # Arrange
    # Set an existing environment variable
    monkeypatch.setenv("MY_EXISTING_VAR", "original_value")

    # Create a temporary .env file in a temporary directory
    env_file = tmp_path / ".env"
    env_file.write_text("MY_EXISTING_VAR=new_value\n")

    # Change to the temporary directory so load_dotenv finds the file
    monkeypatch.chdir(tmp_path)

    # Act
    # The 'load_env' fixture from conftest runs automatically.
    # We just need to check the result.

    # Assert
    assert os.getenv("MY_EXISTING_VAR") == "original_value"

def test_load_env_loads_new_vars(monkeypatch, tmp_path):
    """
    Tests that the load_env fixture correctly loads new variables
    from a .env file if they are not already set in the environment.
    """
    # Arrange
    # Ensure the variable does not exist initially
    monkeypatch.delenv("MY_NEW_VAR", raising=False)

    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("MY_NEW_VAR=loaded_from_file\n")

    # Change to the temporary directory
    monkeypatch.chdir(tmp_path)

    # Act
    # The 'load_env' fixture runs automatically.

    # Assert
    assert os.getenv("MY_NEW_VAR") == "loaded_from_file"
