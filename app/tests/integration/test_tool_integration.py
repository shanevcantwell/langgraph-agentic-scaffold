# app/tests/integration/test_tool_orchestration.py

import pytest
from uuid import uuid4
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# --- Test Blueprint ---
# This test validates the core "Plan and Execute" loop between two specialists.
# It is a Layer 1 Integration Test, focusing on the interaction and data contracts
# between internal components in a controlled environment.
#
# Workflow being tested:
# 1. User provides an instruction ("write a file").
# 2. The RouterSpecialist (Planner) uses its (mocked) LLM to create a plan.
#    - The plan is a structured `ToolMessage`.
# 3. The state containing this plan is passed to the FileSpecialist (Executor).
# 4. The FileSpecialist executes the plan, performing a real file system operation.
# 5. The FileSpecialist reports the result.
#
# This test proves that the data contract (`ToolMessage`) between the planner
# and the executor is sound and that the end-to-end internal workflow is functional.

@pytest.fixture
def router_specialist(initialized_specialist_factory):
    """Provides a RouterSpecialist instance with a mocked LLM adapter."""
    return initialized_specialist_factory("RouterSpecialist", "router_specialist")

@pytest.fixture
def file_specialist(initialized_specialist_factory):
    """Provides a FileSpecialist instance (no LLM, uses real file ops)."""
    return initialized_specialist_factory("FileSpecialist", "file_specialist")

def test_router_plans_and_file_specialist_executes(
    router_specialist, file_specialist, tmp_path: Path
):
    """
    Validates the full internal tool-use cycle:
    RouterSpecialist plans a tool call, and FileSpecialist executes it.
    """
    # === ARRANGE ===

    # 1. Define the user's intent and the target file for the test.
    user_prompt = "Write the text 'hello world' to a file named output.txt"
    target_file_path = tmp_path / "output.txt"
    tool_call_id = f"call_{uuid4()}"

    # 2. Define the mock LLM's response. This is the "plan" the Router will create.
    #    It's an AIMessage containing a tool_calls attribute that specifies
    #    which tool to use (`WriteFileParams`) and with what arguments.
    mock_llm_tool_call = {
        "name": "WriteFileParams",
        "args": {"path": str(target_file_path), "content": "hello world"},
        "id": tool_call_id,
    }
    mock_llm_response = AIMessage(
        content="I will write the file as requested.",
        tool_calls=[mock_llm_tool_call],
    )

    # 3. Configure the RouterSpecialist's mocked LLM to return our predefined plan.
    router_specialist.llm_adapter.invoke.return_value = {
        "ai_message": mock_llm_response
    }

    # === ACT (Phase 1: Planning) ===

    # 4. The initial state contains only the user's request.
    initial_state = {"messages": [HumanMessage(content=user_prompt)]}

    # 5. Invoke the RouterSpecialist. It will call its mock LLM and create the plan.
    intermediate_state = router_specialist._execute_logic(initial_state)

    # === ASSERT (Phase 1: Planning) ===

    # 6. Verify the RouterSpecialist correctly created the ToolMessage plan.
    router_specialist.llm_adapter.invoke.assert_called_once()
    assert "messages" in intermediate_state
    assert len(intermediate_state["messages"]) == 1
    
    plan_message = intermediate_state["messages"][0]
    assert isinstance(plan_message, ToolMessage)
    assert plan_message.name == "WriteFileParams"
    assert plan_message.tool_call_id == tool_call_id
    assert plan_message.additional_kwargs["parsed_args"] == mock_llm_tool_call["args"]

    # === ACT (Phase 2: Handoff & Execution) ===

    # 7. Simulate the graph passing the state. The output of the Router
    #    becomes the input for the FileSpecialist.
    execution_input_state = {"messages": [plan_message]}

    # 8. Invoke the FileSpecialist. It will read the plan and perform the file operation.
    final_state = file_specialist._execute_logic(execution_input_state)

    # === ASSERT (Phase 2: Handoff & Execution) ===

    # 9. Verify the primary side effect: the file was actually created and has the correct content.
    assert target_file_path.is_file()
    assert target_file_path.read_text() == "hello world"

    # 10. Verify the FileSpecialist returned a new ToolMessage reporting its success.
    #     This "closes the loop" by providing feedback on the executed plan.
    assert "messages" in final_state
    assert len(final_state["messages"]) == 1

    result_message = final_state["messages"][0]
    assert isinstance(result_message, ToolMessage)
    assert result_message.tool_call_id == tool_call_id
    assert "Successfully wrote file" in result_message.content
    assert str(target_file_path) in result_message.content

def test_file_specialist_safety_mode_simulation(
    file_specialist, tmp_path: Path, monkeypatch
):
    """
    Validates that when the safety lock is ON, the FileSpecialist simulates
    the file write, reports correctly, and does NOT terminate the workflow.
    """
    # === ARRANGE ===

    # 1. Define the file path and the tool call plan.
    target_file_path = tmp_path / "output_safety.txt"
    tool_call_id = f"call_{uuid4()}"
    tool_message_plan = ToolMessage(
        name="WriteFileParams",
        content="",
        tool_call_id=tool_call_id,
        additional_kwargs={
            "parsed_args": {
                "path": str(target_file_path),
                "content": "this should not be written",
            }
        },
    )
    execution_input_state = {"messages": [tool_message_plan]}

    # 2. Simulate the "safety lock" being engaged.
    #    (This assumes the specialist checks an environment variable.
    #    If it uses a config flag, we would patch that instead.)
    monkeypatch.setenv("AGENT_SAFETY_MODE", "enabled")

    # === ACT ===

    # 3. Invoke the FileSpecialist with the safety lock on.
    result_state = file_specialist._execute_logic(execution_input_state)

    # === ASSERT ===

    # 4. CRITICAL: Assert that the file was NOT actually created.
    assert not target_file_path.is_file()

    # 5. CRITICAL: Assert that the specialist did NOT return the termination signal.
    assert "task_is_complete" not in result_state

    # 6. Assert that the specialist reported the simulation in the scratchpad.
    assert "scratchpad" in result_state
    scratchpad = result_state["scratchpad"]
    assert "file_specialist_safety_note" in scratchpad
    assert "safety mode is on" in scratchpad["file_specialist_safety_note"]
    assert str(target_file_path) in scratchpad["file_specialist_safety_note"]

    # 7. Assert that the specialist returned a ToolMessage with the simulation result.
    assert "messages" in result_state
    result_message = result_state["messages"][0]
    assert isinstance(result_message, ToolMessage)
    assert result_message.tool_call_id == tool_call_id
    assert "Simulated file write" in result_message.content
