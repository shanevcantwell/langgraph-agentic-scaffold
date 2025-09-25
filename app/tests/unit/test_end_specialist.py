import pytest
from unittest.mock import MagicMock, patch, ANY
from langchain_core.messages import AIMessage, HumanMessage
from app.src.specialists.end_specialist import EndSpecialist
from app.src.specialists.response_synthesizer_specialist import ResponseSynthesizerSpecialist
from app.src.specialists.archiver_specialist import ArchiverSpecialist
from app.src.llm.factory import AdapterFactory

@pytest.fixture
def mock_response_synthesizer():
    """Mock for ResponseSynthesizerSpecialist."""
    mock_synthesizer = MagicMock(spec=ResponseSynthesizerSpecialist)
    # Default behavior for _execute_logic
    mock_synthesizer._execute_logic.return_value = {
        "messages": [AIMessage(content="Synthesized response.")],
        "artifacts": {"final_user_response.md": "Synthesized response."},
        "scratchpad": {"user_response_snippets": []}
    }
    return mock_synthesizer

@pytest.fixture
def mock_archiver_specialist():
    """Mock for ArchiverSpecialist."""
    mock_archiver = MagicMock(spec=ArchiverSpecialist)
    # Default behavior for _execute_logic
    mock_archiver._execute_logic.return_value = {
        "artifacts": {"archive_report.md": "Archived data."}
    }
    return mock_archiver

@pytest.fixture
def end_specialist(mock_adapter_factory, mock_response_synthesizer, mock_archiver_specialist):
    """Fixture for an initialized EndSpecialist with mocked internal specialists."""
    specialist_name = "end_specialist"
    specialist_config = {
        "response_synthesizer_specialist": {"llm_config": "default_llm", "prompt_file": "synth_prompt.md"},
        "archiver_specialist": {}
    }

    # Patch the classes that EndSpecialist instantiates internally
    with patch('app.src.specialists.end_specialist.ResponseSynthesizerSpecialist', return_value=mock_response_synthesizer), \
         patch('app.src.specialists.end_specialist.ArchiverSpecialist', return_value=mock_archiver_specialist), \
         patch('app.src.utils.prompt_loader.load_prompt', return_value="Fake prompt"): # Mock prompt loading for synthesizer
        
        specialist = EndSpecialist(
            specialist_name=specialist_name,
            specialist_config=specialist_config,
            adapter_factory=mock_adapter_factory # Pass the factory from conftest
        )
        # The EndSpecialist itself doesn't use its own llm_adapter directly in _execute_logic,
        # but it creates adapters for its internal specialists.
        return specialist

def test_end_specialist_orchestrates_synthesis_and_archiving(end_specialist, mock_response_synthesizer, mock_archiver_specialist):
    """Tests that EndSpecialist calls its internal specialists in order."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Finalize this."), AIMessage(content="Some output.", name="some_specialist")],
        "scratchpad": {"user_response_snippets": ["Snippet 1", "Snippet 2"]}
    }

    # Act
    result_state = end_specialist._execute_logic(initial_state)

    # Assert
    mock_response_synthesizer._execute_logic.assert_called_once()
    mock_archiver_specialist._execute_logic.assert_called_once()

    # Check that the state was updated by both
    assert "final_user_response.md" in result_state["artifacts"]
    assert "archive_report.md" in result_state["artifacts"]
    assert "Synthesized response." in result_state["messages"][-1].content # Last message from synthesizer
    assert result_state["scratchpad"]["user_response_snippets"] == [] # Synthesizer clears snippets

def test_end_specialist_synthesizes_from_last_ai_message_if_no_snippets(end_specialist, mock_response_synthesizer):
    """Tests that if no snippets, it synthesizes from the last non-orchestrator AI message."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="User query."), AIMessage(content="Router decision.", name="router_specialist"), AIMessage(content="Triage decision.", name="prompt_triage_specialist"), AIMessage(content="Important AI output.", name="worker_specialist"), AIMessage(content="Another router decision.", name="router_specialist")],
        "scratchpad": {} # No snippets
    }

    # Act
    end_specialist._execute_logic(initial_state)

    # Assert
    mock_response_synthesizer._execute_logic.assert_called_once()
    # Check that the state passed to synthesizer had the last AI message content in snippets
    synthesizer_call_state = mock_response_synthesizer._execute_logic.call_args[0][0]
    assert "user_response_snippets" in synthesizer_call_state["scratchpad"]
    assert synthesizer_call_state["scratchpad"]["user_response_snippets"] == ["Important AI output."]

def test_end_specialist_skips_synthesis_if_final_response_exists(end_specialist, mock_response_synthesizer, mock_archiver_specialist):
    """Tests that synthesis is skipped if final_user_response.md already exists."""
    # Arrange
    initial_state = {"messages": [HumanMessage(content="Already done.")], "artifacts": {"final_user_response.md": "Pre-existing final response."}}

    # Act
    end_specialist._execute_logic(initial_state)

    # Assert
    mock_response_synthesizer._execute_logic.assert_not_called()
    mock_archiver_specialist._execute_logic.assert_called_once() # Archiver should still run