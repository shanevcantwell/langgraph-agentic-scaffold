import pytest
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
# Assuming SpecialistNode is BaseSpecialist or compatible for instantiation
from app.src.specialists.hello_world_specialist import HelloWorldSpecialist
from app.src.graph.state import GraphState # Assuming GraphState is available

@pytest.fixture
def hello_world_specialist(initialized_specialist_factory):
    """Fixture for an initialized HelloWorldSpecialist."""
    # The factory will instantiate it, even if it overrides 'execute' directly
    return initialized_specialist_factory("HelloWorldSpecialist")

def test_hello_world_specialist_greets_user(hello_world_specialist):
    """Tests that the specialist generates a greeting based on the last message."""
    # Arrange
    user_message_content = "What's up?"
    initial_state = GraphState(messages=[HumanMessage(content=user_message_content)])

    # Act
    # Calling 'execute' directly as per the specialist's implementation
    result_state = hello_world_specialist._execute_logic(initial_state)

    # Assert
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    expected_response = f"Hello from the class-based specialist! You said: '{user_message_content}'"
    assert result_state["messages"][0].content == expected_response

def test_hello_world_specialist_handles_empty_messages(hello_world_specialist):
    """Tests that the specialist provides a default response if state has no messages."""
    # Arrange
    initial_state = GraphState(messages=[])

    # Act
    result_state = hello_world_specialist._execute_logic(initial_state)

    # Assert
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    expected_response = "Hello from the class-based specialist! You said: 'you said nothing'"
    assert result_state["messages"][0].content == expected_response