import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.researcher_specialist import ResearcherSpecialist
from langchain_core.messages import HumanMessage

@pytest.fixture
def researcher(mock_llm_adapter):
    config = {
        "llm_config": "test_config",
        "prompt_file": "test_prompt.md"
    }
    with patch("app.src.specialists.researcher_specialist.load_prompt", return_value="Test Prompt"):
        specialist = ResearcherSpecialist("researcher_specialist", config)
        specialist.llm_adapter = mock_llm_adapter
        return specialist

@pytest.fixture
def mock_llm_adapter():
    return MagicMock()

def test_researcher_performs_search(researcher, mock_llm_adapter):
    # Arrange
    state = {
        "messages": [HumanMessage(content="Search for LangGraph.")]
    }
    
    mock_llm_adapter.invoke.return_value = {
        "tool_calls": [
            {
                "name": "SearchQuery",
                "args": {"query": "LangGraph", "max_results": 3}
            }
        ]
    }
    
    # Act
    result = researcher.execute(state)
    
    # Assert
    assert "artifacts" in result
    assert "search_results" in result["artifacts"]
    results = result["artifacts"]["search_results"]
    assert len(results) == 2 # Mock returns 2 results
    assert "LangGraph" in results[0]["title"]

def test_researcher_registers_mcp(researcher):
    registry = MagicMock()
    researcher.register_mcp_services(registry)
    registry.register_service.assert_called_once()
    args = registry.register_service.call_args[0]
    assert args[0] == "researcher_specialist"
    assert "search" in args[1]

def test_researcher_handles_no_messages(researcher):
    state = {"messages": []}
    result = researcher.execute(state)
    assert result == {}
