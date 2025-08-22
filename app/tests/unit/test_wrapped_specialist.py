import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists.wrapped_specialist import WrappedSpecialist

# Common fixtures for mocking specialist dependencies
@pytest.fixture
def mock_config_loader():
    """Mocks ConfigLoader and returns a mock config dictionary."""
    with patch('app.src.specialists.base.ConfigLoader') as mock_loader:
        mock_config = {
            "source": "/fake/path/to/agent.py",
            "class_name": "FakeAgent"
        }
        mock_loader.return_value.get_specialist_config.return_value = mock_config
        mock_loader.return_value.get_provider_config.return_value = {}
        yield mock_loader, mock_config

@pytest.fixture
def mock_adapter_factory():
    with patch('app.src.specialists.base.AdapterFactory') as mock_factory:
        yield mock_factory

@pytest.fixture
def mock_load_prompt():
    with patch('app.src.specialists.base.load_prompt') as mock_load:
        mock_load.return_value = "" # Wrapped specialists may not have prompts
        yield mock_load

# We need to patch os.path.exists for the WrappedSpecialist's __init__
@patch('os.path.exists', return_value=True)
@patch('importlib.util.spec_from_file_location')
@patch('importlib.util.module_from_spec')
def test_wrapped_specialist_loads_successfully(mock_module_from_spec, mock_spec_from_file_location, mock_os_exists, mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Tests that the WrappedSpecialist initializes correctly when the source file exists."""
    # Arrange
    mock_spec = MagicMock()
    mock_spec_from_file_location.return_value = mock_spec
    mock_module = MagicMock()
    mock_module.FakeAgent = MagicMock() # The class we expect to find
    mock_module_from_spec.return_value = mock_module

    # Act
    specialist = WrappedSpecialist(specialist_name="wrapped_test")

    # Assert
    assert specialist.is_enabled is True
    assert specialist.external_agent is not None
    mock_spec_from_file_location.assert_called_with("external_agent", "/fake/path/to/agent.py")
    mock_spec.loader.exec_module.assert_called_with(mock_module)

@patch('os.path.exists', return_value=False)
def test_wrapped_specialist_disables_if_source_not_found(mock_os_exists, mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Tests that the specialist is disabled if the source file does not exist."""
    # Act
    specialist = WrappedSpecialist(specialist_name="wrapped_test")

    # Assert
    assert specialist.is_enabled is False
    assert specialist.external_agent is None

@patch('os.path.exists', return_value=True)
@patch('importlib.util.spec_from_file_location')
@patch('importlib.util.module_from_spec')
def test_wrapped_specialist_disables_if_class_not_found(mock_module_from_spec, mock_spec_from_file_location, mock_os_exists, mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Tests that the specialist is disabled if the specified class is not in the module."""
    # Arrange
    mock_spec = MagicMock()
    mock_spec_from_file_location.return_value = mock_spec
    mock_module = MagicMock()
    # Deliberately do not add the FakeAgent class to the mock module
    del mock_module.FakeAgent

    # Act
    specialist = WrappedSpecialist(specialist_name="wrapped_test")

    # Assert
    assert specialist.is_enabled is False
    assert specialist.external_agent is None

def test_execute_logic_when_disabled(mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Tests that execute returns an error when the specialist is disabled."""
    # Arrange
    # We need to patch os.path.exists to simulate the disabled state
    with patch('os.path.exists', return_value=False):
        specialist = WrappedSpecialist(specialist_name="wrapped_test")
    
    assert specialist.is_enabled is False # Pre-condition check

    # Act
    result_state = specialist._execute_logic(state={})

    # Assert
    assert "error" in result_state
    assert "is not enabled" in result_state["error"]
