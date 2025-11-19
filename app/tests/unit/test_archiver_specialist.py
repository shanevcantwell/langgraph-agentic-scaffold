import os
import pytest
from unittest.mock import patch, MagicMock, mock_open, ANY
from app.src.specialists.archiver_specialist import ArchiverSpecialist
from app.src.graph.state_factory import create_test_state

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
    return create_test_state(
        routing_history=["some_specialist", "end_specialist"],
        turn_count=2,
        artifacts={
            "final_user_response.md": "This is the final response.",
            "some_code.py": "print('hello')",
            "ignored_dict_artifact": {"key": "value"} # Should be skipped by archiver
        },
        scratchpad={"_called_by_end_specialist": True}
    )

def test_create_atomic_package_structure(archiver_specialist, initial_state):
    """Tests that _create_atomic_package creates the correct file structure and zip."""
    report_md = "# Test Report"
    
    # Mock all the file system operations
    with patch("os.makedirs") as mock_makedirs, \
         patch("builtins.open", mock_open()) as mock_file, \
         patch("os.path.getsize", return_value=100), \
         patch("shutil.make_archive", return_value="/path/to/archive.zip") as mock_make_archive, \
         patch("shutil.rmtree") as mock_rmtree, \
         patch("os.path.exists", return_value=True): # For cleanup check

        zip_path = archiver_specialist._create_atomic_package(initial_state, report_md)

        # Verify zip creation
        assert zip_path == "/path/to/archive.zip"
        mock_make_archive.assert_called_once()
        
        # Verify cleanup
        mock_rmtree.assert_called_once()

        # Verify file writes
        # We expect writes for: report.md, some_code.py, manifest.json
        # final_user_response.md is also in artifacts, so it should be written too.
        # ignored_dict_artifact should be skipped.
        
        # Get all file paths opened
        opened_paths = [call.args[0] for call in mock_file.call_args_list if call.args]
        
        # Check for report.md
        assert any("report.md" in str(p) for p in opened_paths)
        
        # Check for artifacts
        assert any("some_code.py" in str(p) for p in opened_paths)
        assert any("final_user_response.md" in str(p) for p in opened_paths)
        
        # Check for manifest.json
        assert any("manifest.json" in str(p) for p in opened_paths)

def test_execute_logic_creates_package_and_updates_state(archiver_specialist, initial_state):
    """Tests the main logic flow: package creation and state update."""
    expected_zip_path = "/tmp/test_archive.zip"
    
    with patch.object(archiver_specialist, "_create_atomic_package", return_value=expected_zip_path) as mock_create_pkg, \
         patch.object(archiver_specialist, "_prune_archive") as mock_prune:
        
        result = archiver_specialist._execute_logic(initial_state)
        
        # Assert package creation was called
        mock_create_pkg.assert_called_once()
        
        # Assert pruning was called
        mock_prune.assert_called_once()
        
        # Assert artifacts are sanitized (heavy artifacts removed)
        artifacts = result["artifacts"]
        assert "archive_package_path" in artifacts
        assert artifacts["archive_package_path"] == expected_zip_path
        assert "final_user_response.md" in artifacts
        assert "archive_report.md" in artifacts
        
        # Ensure heavy/other artifacts are NOT in the returned state
        assert "some_code.py" not in artifacts
        assert "ignored_dict_artifact" not in artifacts

def test_prune_archive_removes_oldest_files(archiver_specialist):
    """Tests that _prune_archive correctly removes the oldest files."""
    # Create more files than max_archive_files
    mock_files = [f"run_{i}.zip" for i in range(7)]
    
    with patch("os.listdir", return_value=mock_files) as mock_listdir, \
         patch("os.path.getmtime", side_effect=range(len(mock_files))) as mock_getmtime, \
         patch("os.remove") as mock_remove, \
         patch("os.path.join", side_effect=os.path.join): 
        
        archiver_specialist._prune_archive()
        
        mock_listdir.assert_called_once_with(archiver_specialist.archive_dir)
        # Should remove the 2 oldest files to get down to 5
        assert mock_remove.call_count == 2
        mock_remove.assert_any_call(os.path.join(archiver_specialist.archive_dir, "run_0.zip"))
        mock_remove.assert_any_call(os.path.join(archiver_specialist.archive_dir, "run_1.zip"))

def test_execute_logic_handles_missing_final_response(archiver_specialist, initial_state):
    """Tests edge case where final_user_response.md is missing."""
    del initial_state["artifacts"]["final_user_response.md"]
    
    with patch.object(archiver_specialist, "_create_atomic_package", return_value="/zip") as mock_create_pkg, \
         patch.object(archiver_specialist, "_prune_archive"):
        
        result = archiver_specialist._execute_logic(initial_state)
        
        mock_create_pkg.assert_called_once()
        
        # Check that report generation handled the missing response (passed to create_package)
        # We can't easily check the report content passed to create_package without inspecting the mock call args
        call_args = mock_create_pkg.call_args
        report_content = call_args[0][1] # 2nd arg is report_md
        assert "No final response was generated" in report_content
