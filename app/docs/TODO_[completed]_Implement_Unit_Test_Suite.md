# TODO: Implement Full Unit Test Suite

**State:** [to_triage]
**Parent Proposal:** `PROPOSAL_Implement_Testing_Framework.md`

## Objective
To implement a comprehensive unit test suite covering all existing specialists (`FileSpecialist`, `RouterSpecialist`, `DataExtractorSpecialist`, `PromptSpecialist`). This will provide a robust safety net, ensuring system stability and enabling future refactoring and feature development.

## Rationale
This plan executes the core vision of the testing proposal. By creating mocked tests for each specialist, we can validate their logic in isolation, ensuring each component behaves as expected before it is integrated into the larger graph. This is a mandatory prerequisite for complex future work, such as the asynchronous processing model outlined in `PROPOSAL_Architectural_Framework_for_Asynchronous_Task_Processing.md`.

## Step-by-Step Plan

### Step 1: Test `FileSpecialist` (Verification)

The test for `FileSpecialist` is confirmed to be correct against the source code in `file_specialist.py`.

**Create file `tests/unit/test_file_specialist.py`:**
```python
import pytest
from pathlib import Path
from src.specialists.file_specialist import FileSpecialist

@pytest.fixture
def file_specialist(tmp_path):
    return FileSpecialist(root_dir=str(tmp_path))

def test_write_and_read_file(file_specialist, tmp_path):
    """Tests that write_file and read_file work in conjunction."""
    file_path = "test.txt"
    content = "Hello, world!"
    file_specialist.write_file(file_path, content)
    
    read_content = file_specialist.read_file(file_path)
    assert read_content == content

def test_read_file_not_found(file_specialist):
    """Tests graceful failure when reading a non-existent file."""
    result = file_specialist.read_file("not_real.txt")
    assert "Error: File not found at" in result

def test_list_files(file_specialist, tmp_path):
    """Tests directory listing."""
    (tmp_path / "file1.txt").touch()
    (tmp_path / "subdir").mkdir()
    
    listing = file_specialist.list_files(".")
    assert "file1.txt" in listing
    assert "subdir/" in listing
