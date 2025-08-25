# app/tests/unit/test_web_builder.py
from unittest.mock import MagicMock
from src.specialists.web_builder import WebBuilder

def test_web_builder_single_cycle():
    """
    Tests the default behavior (1 cycle) where it generates HTML and signals completion.
    """
    # Arrange
    specialist = WebBuilder("web_builder")
    specialist.llm_adapter = MagicMock()
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site."} # No refinement_cycles key
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["html_artifact"] == mock_response["html_document"]
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state
    assert result_state["web_builder_iteration"] is None # Counter is cleaned up

def test_web_builder_multi_cycle_loop():
    """
    Tests the first iteration of a multi-cycle refinement, ensuring it recommends the critic.
    """
    # Arrange
    specialist = WebBuilder("web_builder")
    specialist.llm_adapter = MagicMock()
    mock_response = {"html_document": "<html><body>Refined Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 0 # This is the first run
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert "task_is_complete" not in result_state
    assert result_state["recommended_specialists"] == ["critic_specialist"]
    assert result_state["web_builder_iteration"] == 1

def test_web_builder_multi_cycle_intermediate_loop():
    """
    Tests an intermediate iteration of a multi-cycle refinement, ensuring it recommends the critic.
    """
    # Arrange
    specialist = WebBuilder("web_builder")
    specialist.llm_adapter = MagicMock()
    mock_response = {"html_document": "<html><body>Refined Hello Again</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 1 # This is the second run
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert "task_is_complete" not in result_state
    assert result_state["recommended_specialists"] == ["critic_specialist"]
    assert result_state["web_builder_iteration"] == 2

def test_web_builder_multi_cycle_final():
    """
    Tests the final iteration of a multi-cycle refinement, ensuring it signals completion.
    """
    # Arrange
    specialist = WebBuilder("web_builder")
    specialist.llm_adapter = MagicMock()
    mock_response = {"html_document": "<html><body>Final Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site.", "refinement_cycles": 3},
        "web_builder_iteration": 2 # This is the third and final run (0, 1, 2)
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    assert result_state["task_is_complete"] is True
    assert "recommended_specialists" not in result_state
    assert result_state["web_builder_iteration"] is None # Counter is cleaned up

def test_web_builder_handles_none_iteration_state():
    """
    Tests that the builder correctly handles the case where the iteration
    counter is explicitly set to None in the state, which happens on the
    first run.
    """
    # Arrange
    specialist = WebBuilder("web_builder")
    specialist.llm_adapter = MagicMock()
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}

    initial_state = {
        "messages": [],
        "system_plan": {"description": "Make a site."},
        "web_builder_iteration": None # Explicitly set to None
    }

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    # The main assertion is that this doesn't crash with a TypeError.
    specialist.llm_adapter.invoke.assert_called_once()
    assert result_state["task_is_complete"] is True
    assert result_state["web_builder_iteration"] is None