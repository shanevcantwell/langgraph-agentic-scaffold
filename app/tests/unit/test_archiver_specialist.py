import os
import pytest
from unittest.mock import patch, MagicMock, mock_open
from app.src.specialists.archiver_specialist import ArchiverSpecialist
from app.src.utils.errors import SpecialistError

@pytest.fixture
def specialist_config():
    return {"archive_dir": "test_archives", "max_archive_files": 5}

@pytest.fixture
def archiver_specialist(specialist_config):
    with patch("os.makedirs") as mock_makedirs:
        specialist = ArchiverSpecialist(
            specialist_name="archiver_specialist",
            specialist_config=specialist_config,
        )
        mock_makedirs.assert_called_once_with("test_archives", exist_ok=True)
    return specialist

@pytest.fixture
def initial_state():
    return {
        "messages": [],
        "routing_history": ["start", "end"],
        "turn_count": 2,
        "artifacts": {"final_user_response.md": "This is the final response."},
        "scratchpad": {},
    }

def test_archiver_initialization_creates_directory(specialist_config):
    """Tests that the specialist creates the archive directory on initialization."""
    with patch("os.makedirs") as mock_makedirs:
        ArchiverSpecialist(
            specialist_name="archiver_specialist",
            specialist_config=specialist_config,
        )
        mock_makedirs.assert_called_once_with("test_archives", exist_ok=True)

def test_save_report_writes_to_file(archiver_specialist):
    """Tests that _save_report correctly writes content to a file."""
    mock_file_content = "Test Report"
    with patch("builtins.open", mock_open()) as mocked_file:
        archiver_specialist._save_report(mock_file_content)
        # Check that open was called with the correct path and mode
        assert mocked_file.call_args[0][0].startswith(os.path.join("test_archives", "run_"))
        assert mocked_file.call_args[0][1] == "w"
        # Check that write was called with the content
        mocked_file().write.assert_called_once_with(mock_file_content)

def test_prune_archive_removes_oldest_files(archiver_specialist):
    """Tests that _prune_archive correctly removes the oldest files."""
    # Create more files than max_archive_files
    mock_files = [f"run_{i}.md" for i in range(7)]
    
    with patch("os.listdir", return_value=mock_files) as mock_listdir, \
         patch("os.path.join", side_effect=lambda *args: os.path.join(*args)) as mock_join, \
         patch("os.remove") as mock_remove:
        
        archiver_specialist._prune_archive()
        
        mock_listdir.assert_called_once_with("test_archives")
        # Should remove the 2 oldest files to get down to 5
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call(os.path.join("test_archives", "run_0.md"))
        mock_remove.assert_any_call(os.path.join("test_archives", "run_1.md"))

def test_execute_logic_generates_and_saves_report(archiver_specialist, initial_state):
    """Tests the main logic flow for generating and saving a success report."""
    with patch.object(archiver_specialist, "_save_report") as mock_save, \
         patch.object(archiver_specialist, "_prune_archive") as mock_prune:
        
        result = archiver_specialist._execute_logic(initial_state)
        
        # Assert that the report was generated and passed to _save_report
        mock_save.assert_called_once()
        saved_content = mock_save.call_args[0][0]
        assert "Status: Completed" in saved_content
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
        assert "final_user_response.md: Not found" in saved_content
        assert "archive_report.md" in result["artifacts"]

def test_execute_logic_handles_save_report_error(archiver_specialist, initial_state):
    """Tests that an error during file saving is caught and raises a SpecialistError."""
    with patch.object(archiver_specialist, "_save_report", side_effect=IOError("Disk full")):
        with pytest.raises(SpecialistError) as excinfo:
            archiver_specialist._execute_logic(initial_state)
        assert "Failed to save archive report" in str(excinfo.value)
        assert "Disk full" in str(excinfo.value)
