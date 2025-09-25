# app/tests/unit/test_code_writer_specialist.py
from unittest.mock import ANY
from langchain_core.messages import AIMessage, HumanMessage

# (ADR-TS-001, Task 2.2) This test is refactored to use the centralized
# `initialized_specialist_factory` fixture from conftest.py.

def test_code_writer_specialist_execute(initialized_specialist_factory):
    """
    Tests that the CodeWriterSpecialist correctly invokes the LLM and
    returns the AI's response as a new message.
    """
    # --- Arrange ---
    # 1. Use the factory to get a fully initialized specialist with mocked dependencies.
    # The factory handles mocking ConfigLoader, AdapterFactory, and the llm_adapter.
    specialist = initialized_specialist_factory("CodeWriterSpecialist")

    # 2. Configure the return value for the mocked llm_adapter.
    mock_response = "print('Hello, World!')"
    specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # 3. Define the initial state for the test.
    initial_state = {
        "messages": [HumanMessage(content="Write a hello world script.")]
    }

    # --- Act ---
    # We test the internal `_execute_logic` method directly to isolate the
    # specialist's core functionality from the BaseSpecialist's `execute` wrapper.
    result_state = specialist._execute_logic(initial_state)

    # --- Assert ---
    # 1. Verify that the LLM adapter was called correctly.
    specialist.llm_adapter.invoke.assert_called_once_with(ANY)

    # 2. Verify that the specialist returns only the new message delta.
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    new_message = result_state["messages"][0]
    assert isinstance(new_message, AIMessage)
    assert new_message.content == mock_response
    assert new_message.name == "code_writer_specialist"