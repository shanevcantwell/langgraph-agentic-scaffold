# app/tests/unit/test_end_specialist.py
import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.end_specialist import EndSpecialist
from langchain_core.messages import AIMessage

@pytest.fixture
def mock_adapter_factory_for_end(mock_adapter_factory):
    """Specific mock for EndSpecialist's internal factory usage."""
    mock_llm_adapter = MagicMock()
    mock_adapter_factory.create_adapter.return_value = mock_llm_adapter
    return mock_adapter_factory, mock_llm_adapter

@pytest.fixture
def end_specialist(mock_config_loader, mock_adapter_factory_for_end):
    """Fixture for an initialized EndSpecialist."""
    adapter_factory, _ = mock_adapter_factory_for_end
    
    # Mock configs for the specialists EndSpecialist orchestrates
    mock_config_loader.get_specialist_config.side_effect = [
        {"prompt_file": "synthesizer.md"}, # for response_synthesizer
        {"archive_path": "./archive"}     # for archiver
    ]
    
    # The EndSpecialist's constructor expects to find the configs for the specialists
    # it orchestrates within its own config block.
    end_specialist_config = {
        "response_synthesizer_specialist": {"llm_config": "gemini-test", "prompt_file": "synthesizer.md"},
        "archiver_specialist": {"archive_path": "./archive"}
    }
    specialist = EndSpecialist(
        specialist_name="end_specialist",
        specialist_config=end_specialist_config,
        adapter_factory=adapter_factory
    )
    return specialist

@patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._execute_logic')
def test_end_specialist_orchestrates_synthesis_and_archiving(mock_archive_execute, end_specialist, mock_adapter_factory_for_end):
    """
    Tests that EndSpecialist correctly calls the synthesizer and then the archiver.
    """
    # Arrange
    _, mock_llm_adapter = mock_adapter_factory_for_end
    mock_llm_adapter.invoke.return_value = {"text_response": "Synthesized response."}
    mock_archive_execute.return_value = {"messages": [AIMessage(content="Archive complete.")]}

    initial_state = {
        "messages": [AIMessage(content="Last AI message.")],
        "scratchpad": {"user_response_snippets": ["Snippet 1."]}
    }

    # Act
    result_state = end_specialist._execute_logic(initial_state)

    # Assert
    # 1. Synthesizer's LLM was called
    mock_llm_adapter.invoke.assert_called_once()
    
    # 2. Archiver's logic was called
    mock_archive_execute.assert_called_once()
    
    # 3. Final state contains artifacts from both and archiver's message
    assert "final_user_response.md" in result_state["artifacts"]
    assert result_state["artifacts"]["final_user_response.md"] == "Synthesized response."
    assert "Archive complete." in result_state["messages"][0].content

@patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._execute_logic')
def test_end_specialist_skips_synthesis_if_final_response_exists(mock_archive_execute, end_specialist, mock_adapter_factory_for_end):
    """
    Tests that EndSpecialist skips the synthesis step if a final response artifact
    already exists in the state.
    """
    # Arrange
    _, mock_llm_adapter = mock_adapter_factory_for_end
    mock_archive_execute.return_value = {"messages": [AIMessage(content="Archive complete.")]}

    initial_state = {
        "messages": [],
        "artifacts": {"final_user_response.md": "Pre-existing response."}
    }

    # Act
    result_state = end_specialist._execute_logic(initial_state)

    # Assert
    mock_llm_adapter.invoke.assert_not_called() # Synthesis should be skipped
    mock_archive_execute.assert_called_once()
    assert "Archive complete." in result_state["messages"][0].content