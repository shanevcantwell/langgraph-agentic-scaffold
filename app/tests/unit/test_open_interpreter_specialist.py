# app/tests/unit/test_open_interpreter_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.open_interpreter_specialist import OpenInterpreterSpecialist
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

@pytest.fixture
def open_interpreter_specialist(initialized_specialist_factory):
    """Fixture for an initialized OpenInterpreterSpecialist."""
    return initialized_specialist_factory("OpenInterpreterSpecialist")

@patch('interpreter.interpreter', new_callable=MagicMock)
def test_open_interpreter_specialist_executes_code_successfully(mock_interpreter, open_interpreter_specialist):
    """
    Tests the full plan-and-execute flow for the OpenInterpreterSpecialist.
    """
    # --- Arrange ---
    # 1. Mock the LLM "Plan" phase
    mock_llm_response = {
        "tool_calls": [{
            "name": "CodeExecutionParams",
            "args": {"language": "python", "code": "print('hello')"},
            "id": "call_123"
        }]
    }
    open_interpreter_specialist.llm_adapter.invoke.return_value = mock_llm_response

    # 2. Mock the "Execute" phase
    # The chat method returns a generator, which we mock as an empty list.
    # The results are then read from the .messages attribute on the mock.
    mock_interpreter.chat.return_value = (_ for _ in [])
    mock_interpreter.messages = [{'role': 'computer', 'type': 'output', 'content': 'hello'}]

    initial_state = {"messages": [HumanMessage(content="Run a hello world script")]}

    # --- Act ---
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # --- Assert ---
    # Assert Plan phase
    open_interpreter_specialist.llm_adapter.invoke.assert_called_once()

    # Assert final state
    assert len(result_state["messages"]) == 1
    message = result_state["messages"][0]
    assert isinstance(message, AIMessage)
    assert "I have executed the following python code" in message.content

def test_open_interpreter_specialist_handles_no_tool_call_from_llm(open_interpreter_specialist):
    """Tests that the specialist handles the case where the LLM fails to generate a plan."""
    open_interpreter_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}
    initial_state = {"messages": [HumanMessage(content="Some ambiguous request")]}

    # Act
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # Assert
    assert "failed to produce a valid code plan" in result_state.get("error", "")