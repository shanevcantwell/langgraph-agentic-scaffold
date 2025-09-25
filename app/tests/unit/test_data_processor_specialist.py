import pytest
import json
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.data_processor_specialist import DataProcessorSpecialist

@pytest.fixture
def data_processor_specialist(initialized_specialist_factory):
    """Fixture for an initialized DataProcessorSpecialist."""
    return initialized_specialist_factory("DataProcessorSpecialist")

def test_data_processor_specialist_processes_json_string(data_processor_specialist):
    """Tests processing a JSON string artifact."""
    # Arrange
    initial_json_data = {"key1": "value1", "key2": 123}
    initial_state = {
        "messages": [HumanMessage(content="Process this data.")],
        "json_artifact": json.dumps(initial_json_data)
    }

    # Act
    result_state = data_processor_specialist._execute_logic(initial_state)

    # Assert
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I have processed the data artifact." in result_state["messages"][0].content
    assert "processed_data" in result_state
    assert result_state["processed_data"]["key1"] == "value1"
    assert result_state["processed_data"]["key2"] == 123
    assert result_state["processed_data"]["processed_by"] == "data_processor_specialist"

def test_data_processor_specialist_processes_dict(data_processor_specialist):
    """Tests processing a dictionary artifact."""
    # Arrange
    initial_dict_data = {"item_name": "widget", "quantity": 5}
    initial_state = {
        "messages": [HumanMessage(content="Process this data.")],
        "json_artifact": initial_dict_data
    }

    # Act
    result_state = data_processor_specialist._execute_logic(initial_state)

    # Assert
    assert "messages" in result_state
    assert len(result_state["messages"]) == 1
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "I have processed the data artifact." in result_state["messages"][0].content
    assert "processed_data" in result_state
    assert result_state["processed_data"]["item_name"] == "widget"
    assert result_state["processed_data"]["quantity"] == 5
    assert result_state["processed_data"]["processed_by"] == "data_processor_specialist"

def test_data_processor_specialist_no_json_artifact_raises_error(data_processor_specialist):
    """Tests behavior when no json_artifact is present in state, expecting a TypeError."""
    initial_state = {"messages": [HumanMessage(content="Process nothing.")]}
    with pytest.raises(TypeError):
        data_processor_specialist._execute_logic(initial_state)