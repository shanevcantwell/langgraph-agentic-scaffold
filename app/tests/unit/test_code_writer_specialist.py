from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.code_writer_specialist import CodeWriterSpecialist


def test_code_writer_specialist_execute():
    # Arrange
    specialist = CodeWriterSpecialist("code_writer_specialist")

    # Mock LLM adapter
    specialist.llm_adapter = MagicMock()
    mock_response = "print('Hello, World!')"
    specialist.llm_adapter.invoke.return_value = {"text_response": mock_response}

    # Initial state with a user message
    initial_state = {
        "messages": [HumanMessage(content="Write a hello world script.")]
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_called_once()
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert result_state["messages"][0].content == mock_response
