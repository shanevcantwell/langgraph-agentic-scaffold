import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.summarizer_specialist import SummarizerSpecialist

@pytest.fixture
def summarizer(mock_llm_adapter):
    config = {
        "llm_config": "test_config",
        "prompt_file": "test_prompt.md"
    }
    with patch("app.src.specialists.summarizer_specialist.load_prompt", return_value="Test Prompt"):
        specialist = SummarizerSpecialist("summarizer_specialist", config)
        specialist.llm_adapter = mock_llm_adapter
        return specialist

@pytest.fixture
def mock_llm_adapter():
    return MagicMock()

def test_summarizer_summarizes_text(summarizer, mock_llm_adapter):
    # Arrange
    state = {
        "artifacts": {"text_to_process": "Long text..."}
    }
    
    mock_llm_adapter.invoke.return_value = {
        "text_response": "Short summary."
    }
    
    # Act
    result = summarizer.execute(state)
    
    # Assert
    assert "artifacts" in result
    assert "summary" in result["artifacts"]
    assert result["artifacts"]["summary"] == "Short summary."

def test_summarizer_registers_mcp(summarizer):
    registry = MagicMock()
    summarizer.register_mcp_services(registry)
    registry.register_service.assert_called_once()
    args = registry.register_service.call_args[0]
    assert args[0] == "summarizer_specialist"
    assert "summarize" in args[1]

def test_summarizer_handles_missing_artifact(summarizer):
    state = {"artifacts": {}}
    result = summarizer.execute(state)
    assert "error" in result
