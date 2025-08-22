import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists.router_specialist import RouterSpecialist, Route
from langchain_core.messages import HumanMessage

@pytest.fixture
def mock_config_loader():
    """Mocks the ConfigLoader to prevent file system access during tests."""
    with patch('app.src.specialists.base.ConfigLoader') as mock_loader:
        # Provide a minimal config for the router to initialize
        mock_loader.return_value.get_specialist_config.return_value = {
            "prompt_file": "router_prompt.md"
        }
        mock_loader.return_value.get_provider_config.return_value = {}
        yield mock_loader

@pytest.fixture
def mock_adapter_factory():
    """Mocks the AdapterFactory to prevent LLM client instantiation."""
    with patch('app.src.specialists.base.AdapterFactory') as mock_factory:
        # Mock the adapter that will be attached to the specialist
        mock_adapter = MagicMock()
        mock_factory.return_value.create_adapter.return_value = mock_adapter
        yield mock_factory, mock_adapter

@pytest.fixture
def mock_load_prompt():
    """Mocks the prompt loader."""
    with patch('app.src.specialists.base.load_prompt') as mock_load:
        mock_load.return_value = "Fake router system prompt"
        yield mock_load

@pytest.fixture
def router_specialist(mock_config_loader, mock_adapter_factory, mock_load_prompt):
    """Provides a RouterSpecialist instance with mocked dependencies."""
    specialist = RouterSpecialist(specialist_name="router_specialist")
    # Attach the mocked adapter for use in tests
    specialist.llm_adapter = mock_adapter_factory[1]
    return specialist

def test_router_routes_successfully(router_specialist):
    """
    Tests that the router correctly parses a valid tool call from the LLM
    and returns the chosen specialist.
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Test prompt")], "turn_count": 0}
    mock_tool_call = [{'args': {'next_specialist': 'file_specialist'}}]
    router_specialist.llm_adapter.invoke.return_value = {"tool_calls": mock_tool_call}

    # Act
    result_state = router_specialist._execute_logic(initial_state)

    # Assert
    router_specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["next_specialist"] == "file_specialist"
    assert result_state["turn_count"] == 1

def test_router_handles_no_tool_call(router_specialist):
    """
    Tests that the router correctly falls back to the prompt_specialist
    when the LLM fails to return a tool call.
    """
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Confusing prompt")], "turn_count": 2}
    # Simulate the LLM returning no tool calls
    router_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}

    # Act
    result_state = router_specialist._execute_logic(initial_state)

    # Assert
    router_specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["next_specialist"] == "prompt_specialist"
    assert result_state["turn_count"] == 3 # Ensure turn count is still incremented