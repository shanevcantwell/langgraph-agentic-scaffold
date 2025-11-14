# app/tests/unit/test_web_builder.py
import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch
from app.src.specialists.web_builder import WebBuilder
from app.src.utils.errors import LLMInvocationError

@pytest.fixture
def specialist(initialized_specialist_factory):
    """Fixture for an initialized WebBuilder with a mocked adapter."""
    return initialized_specialist_factory("WebBuilder")

def test_web_builder_generates_html(specialist):
    """
    Tests that the WebBuilder correctly invokes the LLM with the current
    state and generates an HTML artifact.
    """
    # Arrange
    mock_response = {"html_document": "<html><body>Hello</body></html>"}
    specialist.llm_adapter.invoke.return_value = {"json_response": mock_response}
    initial_state = {"messages": []}

    # Act
    result_state = specialist._execute_logic(initial_state)

    # Assert
    # It should call the LLM with the messages from the state.
    specialist.llm_adapter.invoke.assert_called_once()
    # It should place the generated HTML into the artifacts.
    assert result_state["artifacts"]["html_document.html"] == mock_response["html_document"]
    # It should always recommend the critic to review its work (Task 2.7: moved to scratchpad).
    assert result_state["scratchpad"]["recommended_specialists"] == ["critic_specialist"]
    # Task 2.7: routing_history is now tracked centrally by GraphOrchestrator.safe_executor, not by specialists
    assert "routing_history" not in result_state

def test_web_builder_handles_llm_invocation_error(specialist):
    """Tests that an LLMInvocationError is propagated correctly."""
    # Arrange
    specialist.llm_adapter.invoke.side_effect = LLMInvocationError("API is down")
    initial_state = {"messages": []}

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API is down"):
        specialist._execute_logic(initial_state)

@pytest.mark.parametrize("bad_response", [
    {"json_response": {"wrong_key": "no html"}},
    {"json_response": None},
    {"text_response": "just text"}
], ids=["wrong_key", "no_json", "text_response_instead"])
def test_web_builder_handles_malformed_llm_response(specialist, bad_response):
    """Tests that the specialist raises an error if the LLM response is malformed."""
    with patch.object(specialist, 'llm_adapter') as mock_adapter:
        # Arrange
        mock_adapter.invoke.return_value = bad_response
        initial_state = {"messages": []}

        # Act & Assert
        with pytest.raises((ValueError, ValidationError)):
            specialist._execute_logic(initial_state)