# app/tests/unit/test_open_interpreter_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.open_interpreter_specialist import OpenInterpreterSpecialist
from langchain_core.messages import HumanMessage, AIMessage

@pytest.fixture
def open_interpreter_specialist(initialized_specialist_factory):
    """
    Fixture for an initialized OpenInterpreterSpecialist.
    It injects the required 'prompt_file' configuration to ensure the
    specialist can be instantiated correctly for all tests.
    """
    specialist = initialized_specialist_factory("OpenInterpreterSpecialist")
    specialist.specialist_config['prompt_file'] = 'open_interpreter_prompt.md'
    return specialist

@patch('interpreter.interpreter', new_callable=MagicMock, create=True)
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

    # 2. Mock the "Execute" phase. The `chat` method populates the `messages`
    #    attribute on the interpreter instance as it runs. We simulate this by
    #    having the mock function update the mock's `messages` attribute.
    def mock_chat_effect(*args, **kwargs):
        mock_interpreter.messages.append({'role': 'computer', 'type': 'output', 'content': 'hello'})
        return (_ for _ in []) # Return an empty generator for the stream

    mock_interpreter.chat.side_effect = mock_chat_effect
    mock_interpreter.messages = []

    initial_state = {"messages": [HumanMessage(content="Run a hello world script")]}

    # --- Act ---
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # --- Assert ---
    # Assert Plan phase
    open_interpreter_specialist.llm_adapter.invoke.assert_called_once()

    # Assert that force_tool_call was set to True in the request
    request_arg = open_interpreter_specialist.llm_adapter.invoke.call_args[0][0]
    assert hasattr(request_arg, 'force_tool_call')
    assert request_arg.force_tool_call is True

    # Assert final state
    assert len(result_state["messages"]) == 1
    message = result_state["messages"][0]
    assert isinstance(message, AIMessage)
    assert "I have executed the following python code" in message.content
    assert "hello" in message.content
    assert result_state.get("task_is_complete") is True

def test_open_interpreter_specialist_handles_no_tool_call_from_llm(open_interpreter_specialist):
    """Tests that the specialist handles the case where the LLM fails to generate a plan."""
    open_interpreter_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}
    initial_state = {"messages": [HumanMessage(content="Some ambiguous request")]}

    # Act
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # Assert
    assert "failed to produce a valid code plan" in result_state.get("error", "")

@patch('interpreter.interpreter', new_callable=MagicMock, create=True)
def test_open_interpreter_handles_list_files_prompt(mock_interpreter, open_interpreter_specialist):
    """
    Tests that OpenInterpreterSpecialist can correctly plan and execute a
    shell command for a common prompt like 'list files'.
    """
    # --- Arrange ---
    # 1. Mock the LLM "Plan" phase to generate a bash command
    mock_llm_response = {
        "tool_calls": [{
            "name": "CodeExecutionParams",
            "args": {"language": "bash", "code": "ls -F"},
            "id": "call_456"
        }]
    }
    open_interpreter_specialist.llm_adapter.invoke.return_value = mock_llm_response

    # 2. Mock the "Execute" phase to simulate the output of 'ls -F'
    def mock_chat_effect(*args, **kwargs):
        mock_interpreter.messages.append({'role': 'computer', 'type': 'output', 'content': 'README.md\nsrc/\n'})
        return (_ for _ in [])

    mock_interpreter.chat.side_effect = mock_chat_effect
    mock_interpreter.messages = []

    initial_state = {"messages": [HumanMessage(content="List files available")]}

    # --- Act ---
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # --- Assert ---
    # Assert that the final AI message contains the result
    final_message = result_state["messages"][0]
    assert "Result:" in final_message.content
    assert "README.md\nsrc/\n" in final_message.content

    # Assert that the scratchpad was populated for the ResponseSynthesizer
    scratchpad = result_state["scratchpad"]
    assert "user_response_snippets" in scratchpad
    assert "Executed code and got the following result" in scratchpad["user_response_snippets"][0]
    assert "README.md" in scratchpad["user_response_snippets"][0]
    assert result_state.get("task_is_complete") is True

def test_open_interpreter_specialist_raises_error_if_no_prompt_file(initialized_specialist_factory):
    """
    Tests that the specialist raises a ValueError if the 'prompt_file' is
    missing from its configuration, as it's a critical dependency.
    """
    # Arrange: Create a specialist but do NOT add the prompt_file to its config
    specialist = initialized_specialist_factory("OpenInterpreterSpecialist")
    # We can be extra sure by deleting it if the factory ever changes
    if 'prompt_file' in specialist.specialist_config:
        del specialist.specialist_config['prompt_file']

    initial_state = {"messages": [HumanMessage(content="This will fail.")]}
    with pytest.raises(ValueError, match="requires a 'prompt_file'"):
        specialist._execute_logic(initial_state)
