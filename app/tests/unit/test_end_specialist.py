# app/tests/unit/test_end_specialist.py
"""
Tests for EndSpecialist after refactoring to hybrid coordinator.
EndSpecialist now performs synthesis inline using its own LLM adapter
rather than delegating to a separate ResponseSynthesizerSpecialist.
"""
from unittest.mock import MagicMock, ANY, patch
import pytest
from app.src.specialists.end_specialist import EndSpecialist
from langchain_core.messages import AIMessage, ToolMessage
from app.src.specialists.archiver_specialist import ArchiverSpecialist


@pytest.fixture
def end_specialist(initialized_specialist_factory):
    """
    Fixture for an initialized EndSpecialist. The conftest factory now handles
    the complex internal patching required for this specialist.
    """
    return initialized_specialist_factory("EndSpecialist", specialist_name_override="end_specialist")


def test_end_specialist_initialization(end_specialist):
    """
    Verifies that the EndSpecialist correctly initializes its internal components.
    After refactoring, it no longer has a synthesizer instance - it performs
    synthesis inline using its own LLM adapter.
    """
    # EndSpecialist should have an archiver
    assert isinstance(end_specialist.archiver, ArchiverSpecialist)

    # It should have a synthesis prompt file configured
    assert hasattr(end_specialist, 'synthesis_prompt_file')
    assert end_specialist.synthesis_prompt_file == "response_synthesizer_prompt.md"

    # It should have a specialist name
    assert end_specialist.specialist_name == "end_specialist"


def test_end_specialist_orchestrates_synthesis_and_archiving(end_specialist):
    """
    Tests that EndSpecialist correctly performs synthesis inline and then calls archiver.
    """
    # Arrange
    initial_state = {
        "messages": [AIMessage(content="This is the last message from a worker.", name="some_worker")],
        "scratchpad": {"user_response_snippets": ["snippet 1", "snippet 2"]},
        "artifacts": {}
    }

    # Mock the LLM adapter's invoke method (for synthesis)
    mock_llm_response = {"text_response": "Synthesized: snippet 1\n\nsnippet 2"}
    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.invoke.return_value = mock_llm_response
    end_specialist.llm_adapter.model_name = "mock-model"

    # Mock the archiver's _execute_logic (already patched by conftest)
    with patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report content"}}

        # Act
        result_state = end_specialist._execute_logic(initial_state)

        # Assert
        # 1. LLM adapter was called for synthesis
        end_specialist.llm_adapter.invoke.assert_called_once()

        # 2. Archiver was called
        mock_archive.assert_called_once()

        # 3. The state passed to archiver should contain the synthesized response
        state_for_archiver = mock_archive.call_args[0][0]
        assert "final_user_response.md" in state_for_archiver.get("artifacts", {})
        assert "Synthesized: snippet 1" in state_for_archiver["artifacts"]["final_user_response.md"]

        # 4. The final result should contain the archive artifact
        assert "archive_report.md" in result_state.get("artifacts", {})


def test_end_specialist_skips_synthesis_if_final_response_exists(end_specialist):
    """
    Tests that EndSpecialist skips synthesis if a final response already exists in the state.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "artifacts": {"final_user_response.md": "A pre-existing final response."},
        "scratchpad": {}
    }

    # Mock LLM adapter
    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.model_name = "mock-model"

    with patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report"}}

        # Act
        result_state = end_specialist._execute_logic(initial_state)

        # Assert
        # LLM adapter should NOT be called (synthesis skipped)
        end_specialist.llm_adapter.invoke.assert_not_called()

        # Archiver should still be called
        mock_archive.assert_called_once()

        # Final response should remain the pre-existing one
        state_for_archiver = mock_archive.call_args[0][0]
        assert state_for_archiver["artifacts"]["final_user_response.md"] == "A pre-existing final response."


def test_end_specialist_synthesizes_from_snippets(end_specialist):
    """
    Tests that EndSpecialist correctly synthesizes a response when snippets are present.
    """
    # Arrange
    initial_state = {
        "messages": [],
        "scratchpad": {
            "user_response_snippets": ["First piece", "Second piece", "Third piece"]
        },
        "artifacts": {}
    }

    # Mock LLM response
    mock_llm_response = {"text_response": "Combined: First, Second, and Third pieces"}
    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.invoke.return_value = mock_llm_response
    end_specialist.llm_adapter.model_name = "mock-model"

    with patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report"}}

        # Act
        result_state = end_specialist._execute_logic(initial_state)

        # Assert
        # LLM was called with concatenated snippets
        call_args = end_specialist.llm_adapter.invoke.call_args
        request = call_args[0][0]
        message_content = request.messages[0].content
        assert "First piece" in message_content
        assert "Second piece" in message_content
        assert "Third piece" in message_content

        # Final response contains synthesized text
        state_for_archiver = mock_archive.call_args[0][0]
        assert "Combined: First, Second, and Third pieces" in state_for_archiver["artifacts"]["final_user_response.md"]


def test_end_specialist_handles_empty_snippets_gracefully(end_specialist):
    """
    Tests that EndSpecialist generates a fallback response when no snippets are available.
    """
    # Arrange - state with no snippets
    initial_state = {
        "messages": [AIMessage(content="Some work was done", name="worker")],
        "scratchpad": {"user_response_snippets": []},
        "artifacts": {}
    }

    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.model_name = "mock-model"

    with patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report"}}

        # Act
        result_state = end_specialist._execute_logic(initial_state)

        # Assert
        # Should have generated a fallback response without calling LLM
        state_for_archiver = mock_archive.call_args[0][0]
        assert "final_user_response.md" in state_for_archiver["artifacts"]

        # The fallback should use the last AI message
        final_response = state_for_archiver["artifacts"]["final_user_response.md"]
        assert "Some work was done" in final_response or "completed" in final_response.lower()


def test_end_specialist_handles_termination_reason(end_specialist):
    """
    Tests that EndSpecialist uses explicit termination_reason when present
    (e.g., from loop detection).
    """
    # Arrange
    initial_state = {
        "messages": [],
        "scratchpad": {
            "termination_reason": "Workflow halted due to loop detection.",
            "user_response_snippets": ["Some snippet"]
        },
        "artifacts": {}
    }

    end_specialist.llm_adapter = MagicMock()
    end_specialist.llm_adapter.model_name = "mock-model"

    with patch.object(end_specialist.archiver, '_execute_logic') as mock_archive:
        mock_archive.return_value = {"artifacts": {"archive_report.md": "report"}}

        # Act
        end_specialist._execute_logic(initial_state)

        # Assert
        # Should use termination_reason directly, not call LLM
        end_specialist.llm_adapter.invoke.assert_not_called()

        # Termination reason should be in final response
        state_for_archiver = mock_archive.call_args[0][0]
        assert state_for_archiver["artifacts"]["final_user_response.md"] == "Workflow halted due to loop detection."
