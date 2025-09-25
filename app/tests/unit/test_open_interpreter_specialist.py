import pytest
from unittest.mock import MagicMock, patch, ANY
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.open_interpreter_specialist import OpenInterpreterSpecialist
from app.src.specialists.schemas import CodeExecutionParams
from app.src.llm.adapter import StandardizedLLMRequest

@pytest.fixture
def open_interpreter_specialist(initialized_specialist_factory):
    """Fixture for an initialized OpenInterpreterSpecialist."""
    return initialized_specialist_factory("OpenInterpreterSpecialist")

@pytest.fixture
def mock_interpreter_module():
    """Mock the 'interpreter' module and its behavior."""
    with patch('app.src.specialists.open_interpreter_specialist.interpreter') as mock_interpreter:
        # Configure the mock interpreter module
        mock_interpreter.auto_run = True
        mock_interpreter.llm = MagicMock()
        mock_interpreter.llm.context_window = 0
        mock_interpreter.messages = [] # Simulate the messages list

        # Mock the chat method to return a generator and update messages
        def mock_chat_generator(prompt, display, stream):
            # Simulate the interpreter updating its internal messages list
            mock_interpreter.messages.append({'role': 'user', 'content': prompt})
            mock_interpreter.messages.append({'role': 'computer', 'type': 'output', 'content': 'Simulated output from interpreter.'})
            yield {'role': 'computer', 'type': 'output', 'content': 'Simulated output from interpreter.'} # Yield one chunk
        
        mock_interpreter.chat.side_effect = mock_chat_generator
        yield mock_interpreter

def test_open_interpreter_specialist_executes_code_successfully(open_interpreter_specialist, mock_interpreter_module):
    """Tests successful code generation and execution."""
    # Arrange
    # Mock LLM adapter to return a CodeExecutionParams tool call
    mock_code_params = CodeExecutionParams(language="python", code="print('Hello, OI!')")
    open_interpreter_specialist.llm_adapter.invoke.return_value = {
        "tool_calls": [{"args": mock_code_params.model_dump(), "id": "call_123"}]
    }

    initial_state = {"messages": [HumanMessage(content="Write a Python script to print 'Hello, OI!'")]}

    # Act
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # Assert
    open_interpreter_specialist.llm_adapter.invoke.assert_called_once()
    mock_interpreter_module.chat.assert_called_once_with(
        "Please execute this python code:\n```python\nprint('Hello, OI!')\n```",
        display=False, stream=True
    )
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I have executed the following python code" in result_state["messages"][0].content
    assert "Simulated output from interpreter." in result_state["messages"][0].content

def test_open_interpreter_specialist_handles_no_tool_call_from_llm(open_interpreter_specialist, mock_interpreter_module):
    """Tests handling of LLM failing to provide a tool call."""
    # Arrange
    open_interpreter_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}

    initial_state = {"messages": [HumanMessage(content="Do something.")]}

    # Act
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # Assert
    open_interpreter_specialist.llm_adapter.invoke.assert_called_once()
    mock_interpreter_module.chat.assert_not_called()
    assert "error" in result_state
    assert "failed to produce a valid code plan." in result_state["error"]

def test_open_interpreter_specialist_handles_import_error(open_interpreter_specialist):
    """Tests handling of 'open-interpreter' not being installed."""
    # Arrange
    # Temporarily remove 'interpreter' from sys.modules to simulate ImportError
    with patch.dict('sys.modules', {'interpreter': None}), \
         patch('builtins.__import__', side_effect=ImportError("No module named 'interpreter'")):
        
        initial_state = {"messages": [HumanMessage(content="Run code.")]}

        # Act
        result_state = open_interpreter_specialist._execute_logic(initial_state)

        # Assert
        assert "error" in result_state
        assert "Required package 'open-interpreter' is not installed." in result_state["error"]
        open_interpreter_specialist.llm_adapter.invoke.assert_not_called() # Should not even try to plan

def test_open_interpreter_specialist_requires_llm_adapter(initialized_specialist_factory):
    """Tests that the specialist raises an error if no LLM adapter is bound."""
    specialist = initialized_specialist_factory("OpenInterpreterSpecialist")
    specialist.llm_adapter = None # Explicitly set to None
    initial_state = {"messages": [HumanMessage(content="Run code.")]}
    with pytest.raises(RuntimeError, match="requires an LLM adapter to generate code"):
        specialist._execute_logic(initial_state)