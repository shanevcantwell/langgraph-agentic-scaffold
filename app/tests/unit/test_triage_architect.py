import pytest
from unittest.mock import MagicMock, patch
from app.src.specialists.triage_architect import TriageArchitect
from app.src.interface.context_schema import ContextPlan, ContextAction, ContextActionType
from langchain_core.messages import HumanMessage

@pytest.fixture
def mock_llm_adapter():
    adapter = MagicMock()
    return adapter

@pytest.fixture
def triage_architect(mock_llm_adapter):
    config = {
        "llm_config": "test_config",
        "prompt_file": "test_prompt.md"
    }
    # We don't need to patch LLMFactory anymore
    with patch("app.src.specialists.triage_architect.load_prompt", return_value="Test Prompt"):
        specialist = TriageArchitect("triage_architect", config)
        # Manually attach the adapter (simulating GraphBuilder)
        specialist.llm_adapter = mock_llm_adapter
        return specialist

def test_triage_architect_generates_plan(triage_architect, mock_llm_adapter):
    # Arrange
    state = {
        "messages": [HumanMessage(content="Read the README file.")]
    }
    
    expected_plan = {
        "reasoning": "User asked to read a file.",
        "actions": [
            {
                "type": "read_file",
                "target": "README.md",
                "description": "Read the README"
            }
        ]
    }
    
    mock_llm_adapter.invoke.return_value = {
        "tool_calls": [
            {
                "name": "ContextPlan",
                "args": expected_plan
            }
        ]
    }
    
    # Act
    result = triage_architect.execute(state)
    
    # Assert
    assert "artifacts" in result
    assert "context_plan" in result["artifacts"]
    plan = result["artifacts"]["context_plan"]
    assert plan["reasoning"] == "User asked to read a file."
    assert len(plan["actions"]) == 1
    assert plan["actions"][0]["type"] == "read_file"
    assert plan["actions"][0]["target"] == "README.md"

def test_triage_architect_handles_no_messages(triage_architect):
    state = {"messages": []}
    result = triage_architect.execute(state)
    assert result == {}

def test_triage_architect_handles_llm_error(triage_architect, mock_llm_adapter):
    state = {"messages": [HumanMessage(content="Hello")]}
    mock_llm_adapter.invoke.side_effect = Exception("LLM Error")
    
    result = triage_architect.execute(state)
    assert "error" in result
    assert result["error"] == "LLM Error"
