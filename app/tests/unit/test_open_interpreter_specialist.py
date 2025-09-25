# app/tests/unit/test_open_interpreter_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.open_interpreter_specialist import OpenInterpreterSpecialist
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

@pytest.fixture
def open_interpreter_specialist(initialized_specialist_factory):
    """Fixture for an initialized OpenInterpreterSpecialist."""
    return initialized_specialist_factory("OpenInterpreterSpecialist")

@patch('app.src.specialists.open_interpreter_specialist.interpreter')
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

    initial_state = {"messages": [HumanMessage(content="Run a hello world script")]}

    # --- Act ---
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # --- Assert ---
    # Assert Plan phase
    open_interpreter_specialist.llm_adapter.invoke.assert_called_once()

    # Assert final state
    assert len(result_state["messages"]) == 1
    ai_message = result_state["messages"][0]
    assert isinstance(ai_message, AIMessage)
    assert "I have executed the following python code" in ai_message.content
    assert "print('hello')" in ai_message.content
    # The mock for the interpreter's output is now implicitly handled by the patch
    # and we assert the final AI message content.

def test_open_interpreter_specialist_handles_no_tool_call_from_llm(open_interpreter_specialist):
    """Tests that the specialist handles the case where the LLM fails to generate a plan."""
    open_interpreter_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}
    initial_state = {"messages": [HumanMessage(content="Some ambiguous request")]}
    result_state = open_interpreter_specialist._execute_logic(initial_state)
    assert "failed to produce a valid code plan" in result_state["error"]