import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
from app.src.specialists.archiver_specialist import ArchiverSpecialist

@pytest.fixture
def archiver_specialist(tmp_path, initialized_specialist_factory):
    """
    Provides an ArchiverSpecialist instance, mocking the environment variable
    to point its archive directory to a temporary path for isolated testing.
    """
    archive_dir = tmp_path / "test_archives"

    with patch.dict(os.environ, {"AGENTIC_SCAFFOLD_ARCHIVE_PATH": str(archive_dir)}):
        specialist = initialized_specialist_factory(
            "ArchiverSpecialist",
            specialist_name_override="archiver_specialist",
            config_override={
                "pruning_strategy": "count",
                "pruning_max_count": 5,
            },
        )
        return specialist

@pytest.fixture
def initial_state():
    return {
        "messages": [],
        "routing_history": ["some_specialist", "end_specialist"],
        "turn_count": 2,
        "artifacts": {"final_user_response.md": "This is the final response."},
        "scratchpad": {"_called_by_end_specialist": True},  # Simulate internal call
    }

def test_save_report_writes_to_file(archiver_specialist):
    """Tests that _save_report correctly writes content to a file."""
    mock_file_content = "Test Report"
    with patch("builtins.open", mock_open()) as mocked_file:
        archiver_specialist._save_report(mock_file_content)
        # Check that open was called with the correct path and mode
        assert archiver_specialist.archive_dir in mocked_file.call_args[0][0]
        assert mocked_file.call_args[0][1] == "w"
        # Check that write was called with the content
        mocked_file().write.assert_called_once_with(mock_file_content)

def test_prune_archive_removes_oldest_files(archiver_specialist):
    """Tests that _prune_archive correctly removes the oldest files."""
    # Create more files than max_archive_files
    mock_files = [f"run_{i}.md" for i in range(7)]
    
    with patch("os.listdir", return_value=mock_files) as mock_listdir, \
         patch("os.path.getmtime", side_effect=range(len(mock_files))) as mock_getmtime, \
         patch("os.remove") as mock_remove, \
         patch("os.path.join", side_effect=os.path.join): # Use the real os.path.join
        
        archiver_specialist._prune_archive()
        
        mock_listdir.assert_called_once_with(archiver_specialist.archive_dir)
        # Should remove the 2 oldest files to get down to 5
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call(os.path.join(archiver_specialist.archive_dir, "run_0.md"))
        mock_remove.assert_any_call(os.path.join(archiver_specialist.archive_dir, "run_1.md"))

def test_execute_logic_generates_and_saves_report(archiver_specialist, initial_state):
    """Tests the main logic flow for generating and saving a success report."""
    with patch.object(archiver_specialist, "_save_report") as mock_save, \
         patch.object(archiver_specialist, "_prune_archive") as mock_prune:
        
        result = archiver_specialist._execute_logic(initial_state)
        
        # Assert that the report was generated and passed to _save_report
        mock_save.assert_called_once()
        saved_content = mock_save.call_args[0][0]
        assert "Final User Response" in saved_content
        assert "This is the final response." in saved_content
        
        mock_prune.assert_called_once()
        
        # Assert the final artifact is in the state
        assert "archive_report.md" in result["artifacts"]
        assert result["artifacts"]["archive_report.md"] == saved_content

def test_execute_logic_handles_missing_final_response(archiver_specialist, initial_state):
    """Tests edge case where final_user_response.md is missing from artifacts."""
    del initial_state["artifacts"]["final_user_response.md"]
    
    with patch.object(archiver_specialist, "_save_report") as mock_save, \
         patch.object(archiver_specialist, "_prune_archive"):
        
        result = archiver_specialist._execute_logic(initial_state)
        
        mock_save.assert_called_once()
        saved_content = mock_save.call_args[0][0]
        assert "No final response was generated." in saved_content
        assert "archive_report.md" in result["artifacts"]
