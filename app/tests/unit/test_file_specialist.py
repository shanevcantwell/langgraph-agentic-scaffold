import pytest
from unittest.mock import MagicMock, patch
from src.specialists.file_specialist import FileSpecialist
from langchain_core.messages import AIMessage, HumanMessage
# Architectural Note: The 'tmp_path' fixture is provided by pytest.
# It creates a unique temporary directory for each test function, ensuring that
# tests are isolated and do not interfere with each other or leave artifacts
# on the filesystem. This is the standard best practice for testing file I/O.

@pytest.fixture
def tmp_path_fixture(tmp_path):
    """Provides a temporary directory path."""
    return tmp_path

def test_read_file_happy_path(tmp_path_fixture):
    """Tests successful file reading."""
    file_specialist = FileSpecialist(llm_provider='gemini', root_dir=str(tmp_path_fixture))
    test_file = tmp_path_fixture / "test.txt"
    test_file.write_text("Hello, world!")

    result = file_specialist._read_file_impl(str(test_file))
    assert result == "Hello, world!"

def test_write_file_happy_path(tmp_path_fixture):
    """Tests successful file writing."""
    file_specialist = FileSpecialist(llm_provider='gemini', root_dir=str(tmp_path_fixture))
    test_file = tmp_path_fixture / "test_write.txt"

    result = file_specialist._write_file_impl(str(test_file), "Hello again!")
    assert test_file.read_text() == "Hello again!"
    assert "Successfully wrote" in result

def test_list_directory_happy_path(tmp_path_fixture):
    """Tests successful directory listing."""
    file_specialist = FileSpecialist(llm_provider='gemini', root_dir=str(tmp_path_fixture))
    (tmp_path_fixture / "file1.txt").touch()
    (tmp_path_fixture / "file2.txt").touch()

    result = file_specialist._list_directory_impl(str(tmp_path_fixture))
    assert "file1.txt" in result
    assert "file2.txt" in result

def test_path_traversal_prevention(tmp_path_fixture):
    """Tests that directory traversal is blocked."""
    file_specialist = FileSpecialist(llm_provider='gemini', root_dir=str(tmp_path_fixture))
    with pytest.raises(ValueError, match="directory traversal"):
        file_specialist._get_full_path("../secret.txt")

def test_execute_routes_to_read(tmp_path_fixture):
    """Tests that the specialist correctly interprets an LLM call to read a file."""
    file_specialist = FileSpecialist(llm_provider='gemini', root_dir=str(tmp_path_fixture))

    # Mock the LLM client's invoke method directly
    with patch.object(file_specialist.llm_client, 'invoke') as mock_invoke:
        mock_invoke.return_value = AIMessage(
            content="",
            tool_calls=[{'name': 'read_file', 'args': {'file_path': 'test.txt'}, 'id': 'call_123'}])

        # Mock the actual file operation to isolate the test to the specialist's logic
        file_specialist._read_file_impl = MagicMock(return_value="File content")

        state = {"messages": [HumanMessage(content="Read test.txt")]}
        result = file_specialist.execute(state)

        # Assert that the read_file tool was called and the result is in the output
        file_specialist._read_file_impl.assert_called_once_with(file_path='test.txt')
        assert "File content" in str(result["messages"])