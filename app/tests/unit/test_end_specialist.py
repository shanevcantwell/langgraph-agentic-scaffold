# app/tests/unit/test_end_specialist.py
from unittest.mock import MagicMock, ANY, patch
import pytest
from app.src.specialists.end_specialist import EndSpecialist
from langchain_core.messages import AIMessage
from app.src.specialists.response_synthesizer_specialist import ResponseSynthesizerSpecialist
from app.src.specialists.archiver_specialist import ArchiverSpecialist

@pytest.fixture
def end_specialist(initialized_specialist_factory, mock_adapter_factory):
    """
    Fixture for an initialized EndSpecialist. The conftest factory now handles
    the complex internal patching required for this specialist.
    """
    return initialized_specialist_factory("EndSpecialist", specialist_name_override="end_specialist")

def test_end_specialist_initialization(end_specialist, mock_adapter_factory):
    """
    Verifies that the EndSpecialist correctly initializes its internal specialists
    and provides the synthesizer with an LLM adapter.
    """
    assert isinstance(end_specialist.synthesizer, ResponseSynthesizerSpecialist)
    assert isinstance(end_specialist.archiver, ArchiverSpecialist)
    assert end_specialist.synthesizer.llm_adapter is not None

def test_end_specialist_orchestrates_synthesis_and_archiving(end_specialist):
    """
    Tests that EndSpecialist correctly calls the response synthesizer and then the archiver.
    """
    # Arrange
    initial_state = {
        "messages": [AIMessage(content="This is the last message from a worker.", name="some_worker")],
        "scratchpad": {"user_response_snippets": ["snippet 1", "snippet 2"]},
        "artifacts": {}
    }

    # Mock the internal logic of the orchestrated specialists
    # We patch the _execute_logic methods on the instances created by EndSpecialist
    with patch.object(end_specialist.synthesizer, '_execute_logic') as mock_synthesize, \
         patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:

        # Define what the mocked methods will return
        mock_synthesize.return_value = {"artifacts": {"final_user_response.md": "Synthesized response"}}
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report content"}}

        # Act
        result_state = end_specialist._execute_logic(initial_state)

        # Assert
        # 1. ResponseSynthesizer was called first
        mock_synthesize.assert_called_once()

        # 2. Archiver was called second
        mock_archive.assert_called_once()

        # 3. The state passed to the archiver should contain the result from the synthesizer
        state_for_archiver = mock_archive.call_args[0][0]
        assert "final_user_response.md" in state_for_archiver.get("artifacts", {})

        # 4. The final result should contain the artifact from the archiver
        assert "archive_report.md" in result_state.get("artifacts", {})

def test_end_specialist_skips_synthesis_if_final_response_exists(end_specialist):
    """
    Tests that EndSpecialist skips synthesis if a final response already exists in the state.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "artifacts": {"final_user_response.md": "A pre-existing final response."}
    }

    with patch.object(end_specialist.synthesizer, '_execute_logic') as mock_synthesize, \
         patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:

        # Act
        end_specialist._execute_logic(initial_state)

        # Assert
        mock_synthesize.assert_not_called()
        mock_archive.assert_called_once()