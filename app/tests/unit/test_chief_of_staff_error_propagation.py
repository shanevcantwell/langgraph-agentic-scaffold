import pytest
from unittest.mock import patch
import traceback

from src.specialists.chief_of_staff import ChiefOfStaffSpecialist
from src.specialists.systems_architect import SystemsArchitect
from src.specialists.web_builder import WebBuilder
from src.llm.clients import GeminiClient
from src.llm.factory import LLMClientFactory

@pytest.fixture
def mock_gemini_client_factory(mocker):
    """Fixture to mock LLMClientFactory to return a mocked GeminiClient."""
    mock_client = mocker.Mock(spec=GeminiClient)
    mocker.patch.object(LLMClientFactory, 'create_client', return_value=mock_client)
    return mock_client

def test_gemini_client_error_propagation(mock_gemini_client_factory):
    """
    Tests that an exception raised by GeminiClient propagates correctly
    through the ChiefOfStaffSpecialist and returns detailed error info.
    """
    # Configure the mocked GeminiClient to raise an exception on invoke
    test_exception_message = "Simulated Gemini API error for testing."
    mock_gemini_client_factory.invoke.side_effect = Exception(test_exception_message)

    # Instantiate specialists (they will use the mocked LLMClientFactory)
    systems_architect = SystemsArchitect(llm_provider="gemini")
    web_builder = WebBuilder(llm_provider="gemini")

    chief_of_staff = ChiefOfStaffSpecialist(
        systems_architect=systems_architect,
        web_builder=web_builder
    )

    # Invoke the workflow
    result = chief_of_staff.invoke("Test goal for error propagation.")

    # Assert the result structure and content
    assert result["status"] == "error"
    assert test_exception_message in result["message"]
    assert "Error invoking LLM client" in result["message"]
    assert "Traceback (most recent call last):" in result["details"]
    assert test_exception_message in result["details"]

    # Verify that GeminiClient.invoke was called
    mock_gemini_client_factory.invoke.assert_called_once()
