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


def test_triage_populates_recommended_specialists(triage_architect, mock_llm_adapter):
    """
    Test that TriageArchitect populates recommended_specialists in scratchpad.

    Scenario:
    - User asks for web research
    - Triage recommends researcher_specialist
    - Verify scratchpad.recommended_specialists is populated
    """
    state = {
        "messages": [HumanMessage(content="Research winter weather in Colorado")]
    }

    expected_plan = {
        "reasoning": "User needs web search for weather information",
        "actions": [
            {
                "type": "research",
                "target": "winter weather Colorado",
                "description": "Search for weather patterns"
            }
        ],
        "recommended_specialists": ["researcher_specialist", "chat_specialist"]
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

    # Assert - verify scratchpad contains recommendations
    assert "scratchpad" in result
    assert "recommended_specialists" in result["scratchpad"]
    assert result["scratchpad"]["recommended_specialists"] == ["researcher_specialist", "chat_specialist"]

    # Also verify it's in the artifact
    assert "artifacts" in result
    assert "context_plan" in result["artifacts"]
    assert result["artifacts"]["context_plan"]["recommended_specialists"] == ["researcher_specialist", "chat_specialist"]


def test_triage_empty_recommendations_for_greeting(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect with empty actions still provides recommendations.

    Scenario:
    - User sends greeting ("Hello!")
    - No context gathering needed (empty actions)
    - But should still recommend chat_specialist for response
    """
    state = {
        "messages": [HumanMessage(content="Hello!")]
    }

    expected_plan = {
        "reasoning": "Simple greeting, no context needed",
        "actions": [],
        "recommended_specialists": ["chat_specialist"]
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
    assert result["scratchpad"]["recommended_specialists"] == ["chat_specialist"]
    assert len(result["artifacts"]["context_plan"]["actions"]) == 0


def test_triage_multiple_recommendations(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect can recommend multiple specialists.

    Scenario:
    - Complex task could be handled by multiple specialists
    - Triage recommends 3 specialists for router to choose from
    """
    state = {
        "messages": [HumanMessage(content="Analyze this code and fix any bugs")]
    }

    expected_plan = {
        "reasoning": "User needs code analysis and potentially file modification",
        "actions": [
            {
                "type": "read_file",
                "target": "src/main.py",
                "description": "Read the code"
            }
        ],
        "recommended_specialists": [
            "text_analysis_specialist",
            "file_operations_specialist",
            "chat_specialist"
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
    assert len(result["scratchpad"]["recommended_specialists"]) == 3
    assert "text_analysis_specialist" in result["scratchpad"]["recommended_specialists"]
    assert "file_operations_specialist" in result["scratchpad"]["recommended_specialists"]
    assert "chat_specialist" in result["scratchpad"]["recommended_specialists"]


def test_triage_default_empty_recommendations_if_not_provided(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect handles LLM not providing recommended_specialists.

    Scenario:
    - LLM returns plan without recommended_specialists field
    - Pydantic default should provide empty list
    - Should not crash
    """
    state = {
        "messages": [HumanMessage(content="Do something")]
    }

    # LLM returns plan WITHOUT recommended_specialists
    expected_plan = {
        "reasoning": "User request is ambiguous",
        "actions": []
        # No recommended_specialists field
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

    # Assert - should default to empty list, not crash
    assert "scratchpad" in result
    assert "recommended_specialists" in result["scratchpad"]
    assert result["scratchpad"]["recommended_specialists"] == []
