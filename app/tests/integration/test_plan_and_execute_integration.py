"""
Integration Test: Verifying the "Plan and Execute" Integration Pattern

As per the design document, this test validates the functional correctness and
contract soundness of the "Plan and Execute" workflow. It focuses on the
interaction between a "Planner" component and an "Executor" component.

In this specific implementation, the `OpenInterpreterSpecialist` serves as both
the Planner and the Executor. The test verifies that it can:
1.  **Plan:** Correctly generate a structured code execution plan (`CodeExecutionParams`)
    based on a user request, by mocking the LLM's response.
2.  **Execute:** Correctly interpret that plan and invoke the `open-interpreter`
    library to perform the intended action.

This test isolates the specialist's logic from live LLMs and the full graph,
providing a controlled environment to ensure the data contract between the
planning and execution phases is sound.
"""

import pytest
from unittest.mock import patch, MagicMock, ANY
from langchain_core.messages import HumanMessage


@pytest.fixture
def open_interpreter_specialist(initialized_specialist_factory):
    """
    Provides a fully initialized OpenInterpreterSpecialist with its core
    dependencies (ConfigLoader, AdapterFactory, llm_adapter) mocked.
    """
    return initialized_specialist_factory("OpenInterpreterSpecialist")


def test_plan_and_execute_workflow(open_interpreter_specialist):
    """
    Tests the full "Plan and Execute" workflow within the OpenInterpreterSpecialist.

    - Phase 1 (Planning): Verifies that the specialist correctly uses its LLM
      adapter to generate a structured `CodeExecutionParams` plan.
    - Phase 2 (Execution): Verifies that the specialist correctly uses the generated
      plan to call the `interpreter` library with the right code.
    """
    # --- Arrange ---

    # 1. Define the high-level user intent.
    user_intent = "Write the text 'hello world' to a file named 'test.txt'."
    initial_state = {"messages": [HumanMessage(content=user_intent)]}

    # 2. Define the predefined, ideal plan (the data contract).
    # This is the structured data we expect the "Planner" (the specialist's
    # LLM adapter) to generate.
    mock_plan = {
        "language": "python",
        "code": "with open('test.txt', 'w') as f:\n    f.write('hello world')",
    }

    # 3. Mock the Planner's LLM to return the ideal plan.
    # The `initialized_specialist_factory` has already provided a mock `llm_adapter`.
    # We configure it to return a response containing the `tool_calls` with our plan.
    open_interpreter_specialist.llm_adapter.invoke.return_value = {
        "tool_calls": [{"id": "call_123", "type": "tool_code", "args": mock_plan}]
    }

    # 4. Mock the Executor's external dependency (`interpreter` library).
    # We patch the `interpreter` at the point of import within the method under test.
    # This prevents any real code from running and allows us to assert it was called correctly.
    with patch(
        "interpreter.interpreter", autospec=True
    ) as mock_interpreter:
        # The `chat` method populates the `messages` attribute on the interpreter
        # instance as it runs. We simulate this by having the mock function
        # update the mock's `messages` attribute and return an empty generator.
        simulated_output = {
            "role": "computer",
            "type": "output",
            "content": "File 'test.txt' created successfully.",
        }

        def mock_chat_effect(*args, **kwargs):
            mock_interpreter.messages.append(simulated_output)
            return (_ for _ in [])  # Return an empty generator for the stream

        mock_interpreter.chat.side_effect = mock_chat_effect
        mock_interpreter.messages = []

        # --- Act ---
        # Invoke the specialist's logic, which contains both Plan and Execute phases.
        result_state = open_interpreter_specialist._execute_logic(initial_state)

        # --- Assert ---

        # Phase 1: Planning Verification
        # Confirm the Planner (LLM adapter) was called correctly to generate the plan.
        open_interpreter_specialist.llm_adapter.invoke.assert_called_once()
        # We can inspect the call `ANY` if needed: `open_interpreter_specialist.llm_adapter.invoke.call_args`

        # Phase 2: Execution Verification
        # Confirm the Executor (interpreter library) was called with the correct plan.
        mock_interpreter.chat.assert_called_once()
        call_args, _ = mock_interpreter.chat.call_args
        # The first argument to chat should contain the code from our mock plan.
        assert mock_plan["code"] in call_args[0]
        assert mock_plan["language"] in call_args[0]

        # Confirm the final result message "closes the loop" by reporting the outcome.
        assert "I have executed the following python code" in result_state["messages"][0].content
        assert "File 'test.txt' created successfully." in result_state["messages"][0].content

        # Confirm the task is marked as complete
        assert result_state.get("task_is_complete") is True


def test_plan_and_execute_handles_llm_planning_failure(open_interpreter_specialist):
    """
    Tests that the specialist correctly handles the case where the LLM fails
    to generate a valid plan (e.g., returns no tool calls).
    """
    # --- Arrange ---
    # 1. Define user intent
    user_intent = "This is an ambiguous request that won't map to a tool."
    initial_state = {"messages": [HumanMessage(content=user_intent)]}

    # 2. Mock the Planner's LLM to return an empty response (no tool calls)
    open_interpreter_specialist.llm_adapter.invoke.return_value = {"tool_calls": []}

    # --- Act ---
    result_state = open_interpreter_specialist._execute_logic(initial_state)

    # --- Assert ---
    assert "error" in result_state
    assert "failed to produce a valid code plan" in result_state["error"]