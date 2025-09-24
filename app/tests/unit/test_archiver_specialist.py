# Audit Date: Sept 23, 2025
# app/tests/unit/test_archiver_specialist.py
import pytest
from unittest.mock import patch, MagicMock

from app.src.specialists.archiver_specialist import ArchiverSpecialist
from app.src.specialists.schemas._archiver import SuccessReport

@pytest.fixture
def archiver_specialist():
    """Fixture for an initialized ArchiverSpecialist."""
    with patch('os.makedirs'): # Mock os.makedirs to avoid creating directories
        specialist = ArchiverSpecialist(
            specialist_name="archiver_specialist",
            specialist_config={"type": "procedural"}
        )
    return specialist

@patch('app.src.utils.state_pruner.generate_success_report')
@patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._save_report')
@patch('app.src.specialists.archiver_specialist.ArchiverSpecialist._prune_archive')
def test_archiver_generates_success_report(mock_prune, mock_save, mock_generate_report, archiver_specialist):
    """
    Tests that the archiver correctly prepares a SuccessReport, calls the
    correct report generation function, and returns the final report as an artifact.
    """
    # Arrange
    mock_generate_report.return_value = "# Final Report Content"
    initial_state = {
        "messages": [],
        "routing_history": ["specialist_a", "specialist_b"],
        "artifacts": {
            "final_user_response.md": "This is the final response."
        },
        "scratchpad": {"some_data": 123}
    }

    # Act
    result_state = archiver_specialist._execute_logic(initial_state)

    # Assert
    mock_generate_report.assert_called_once()
    # Check that the argument passed to the report generator is a SuccessReport instance
    report_arg = mock_generate_report.call_args[0][0]
    assert isinstance(report_arg, SuccessReport)
    assert report_arg.final_user_response == "This is the final response."
    
    mock_save.assert_called_once_with("# Final Report Content")
    mock_prune.assert_called_once()

    assert "artifacts" in result_state
    assert result_state["artifacts"]["archive_report.md"] == "# Final Report Content"