import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists import get_specialist_class

def test_get_specialist_class_success():
    """
    Tests that the loader can successfully import and return a class
    when the module and class exist.
    """
    # We test with a real, existing specialist
    from app.src.specialists.router_specialist import RouterSpecialist
    
    loaded_class = get_specialist_class("router_specialist", config={})
    assert loaded_class == RouterSpecialist

@patch('importlib.import_module')
def test_get_specialist_class_import_error(mock_import_module):
    """
    Tests that the loader propagates an ImportError if the specialist
    module does not exist.
    """
    specialist_name = "non_existent_specialist"
    mock_import_module.side_effect = ImportError(f"No module named {specialist_name}")

    with pytest.raises(ImportError):
        get_specialist_class(specialist_name, config={})

    mock_import_module.assert_called_once_with(f".{specialist_name}", package="app.src.specialists")