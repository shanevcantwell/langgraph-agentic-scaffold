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
    # TriageArchitect doesn't load prompts itself - GraphBuilder._configure_triage()
    # handles prompt assembly with dynamic specialist roster
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
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert — triage writes to scratchpad, not artifacts
    assert "scratchpad" in result
    assert result["scratchpad"]["triage_reasoning"] == "User asked to read a file."
    actions = result["scratchpad"]["triage_actions"]
    assert len(actions) == 1
    assert actions[0]["type"] == "read_file"
    assert actions[0]["target"] == "README.md"

def test_triage_architect_handles_no_messages(triage_architect):
    state = {"messages": []}
    result = triage_architect.execute(state)
    assert result == {}

def test_triage_architect_handles_llm_error(triage_architect, mock_llm_adapter):
    """#154: LLM errors should return a valid fallback ContextPlan, not bare {'error': ...}."""
    state = {"messages": [HumanMessage(content="Hello")]}
    mock_llm_adapter.invoke.side_effect = Exception("LLM Error")

    result = triage_architect.execute(state)
    # Must return valid specialist result with scratchpad
    assert "scratchpad" in result
    assert "LLM Error" in result["scratchpad"]["triage_reasoning"]
    assert result["scratchpad"]["triage_actions"] == []


def test_triage_populates_actions_in_scratchpad(triage_architect, mock_llm_adapter):
    """
    Test that TriageArchitect populates triage_actions in scratchpad.

    Scenario:
    - User asks for web research
    - Triage produces a research action
    - Verify scratchpad.triage_actions is populated
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
        ]
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - verify scratchpad contains triage output
    assert "scratchpad" in result
    assert result["scratchpad"]["triage_reasoning"] == "User needs web search for weather information"
    actions = result["scratchpad"]["triage_actions"]
    assert len(actions) == 1
    assert actions[0]["type"] == "research"
    assert actions[0]["target"] == "winter weather Colorado"


def test_triage_empty_actions_for_greeting(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect with empty actions for a simple greeting.

    Scenario:
    - User sends greeting ("Hello!")
    - No context gathering needed (empty actions)
    - Verify scratchpad has empty triage_actions
    """
    state = {
        "messages": [HumanMessage(content="Hello!")]
    }

    expected_plan = {
        "reasoning": "Simple greeting, no context needed",
        "actions": []
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert
    assert result["scratchpad"]["triage_reasoning"] == "Simple greeting, no context needed"
    assert result["scratchpad"]["triage_actions"] == []


def test_triage_multiple_actions(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect can produce multiple actions.

    Scenario:
    - Complex task requires multiple context-gathering steps
    - Triage produces multiple actions
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
            },
            {
                "type": "read_file",
                "target": "src/utils.py",
                "description": "Read utilities"
            },
            {
                "type": "research",
                "target": "common Python bugs",
                "description": "Research common issues"
            }
        ]
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert
    actions = result["scratchpad"]["triage_actions"]
    assert len(actions) == 3
    assert actions[0]["type"] == "read_file"
    assert actions[0]["target"] == "src/main.py"
    assert actions[1]["type"] == "read_file"
    assert actions[1]["target"] == "src/utils.py"
    assert actions[2]["type"] == "research"


def test_triage_empty_actions_default(triage_architect, mock_llm_adapter):
    """
    Test TriageArchitect handles LLM returning empty actions.

    Scenario:
    - LLM returns plan with empty actions list
    - Should produce empty triage_actions, not crash
    """
    state = {
        "messages": [HumanMessage(content="Do something")]
    }

    expected_plan = {
        "reasoning": "User request is ambiguous",
        "actions": []
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - should have empty actions list, not crash
    assert "scratchpad" in result
    assert result["scratchpad"]["triage_reasoning"] == "User request is ambiguous"
    assert result["scratchpad"]["triage_actions"] == []


def test_triage_handles_malformed_actions_field(triage_architect, mock_llm_adapter):
    """#154: LLM returns actions as string instead of list — should not crash."""
    state = {"messages": [HumanMessage(content="Do something")]}

    mock_llm_adapter.invoke.return_value = {
        "json_response": {
            "reasoning": "A plan",
            "actions": "not a list"  # Malformed
        }
    }

    result = triage_architect.execute(state)
    assert "scratchpad" in result
    # Malformed actions replaced with empty list
    assert result["scratchpad"]["triage_actions"] == []
    assert result["scratchpad"]["triage_reasoning"] == "A plan"


def test_triage_handles_empty_json_response(triage_architect, mock_llm_adapter):
    """#154: LLM returns empty JSON — should return fallback, not crash."""
    state = {"messages": [HumanMessage(content="Hello")]}

    mock_llm_adapter.invoke.return_value = {"json_response": {}}

    result = triage_architect.execute(state)
    assert "scratchpad" in result
    assert "fallback" in result["scratchpad"]["triage_reasoning"].lower()
    assert result["scratchpad"]["triage_actions"] == []


def test_triage_handles_validation_error(triage_architect, mock_llm_adapter):
    """#154: Pydantic rejects args — salvage what we can (reasoning preserved)."""
    state = {"messages": [HumanMessage(content="Do something")]}

    mock_llm_adapter.invoke.return_value = {
        "json_response": {
            "reasoning": "A plan",
            "actions": [{"type": "INVALID_TYPE", "target": "x"}]  # Will fail ContextAction validation
        }
    }

    result = triage_architect.execute(state)
    assert "scratchpad" in result
    # Salvage: reasoning preserved despite validation failure, actions defaulted to empty
    assert result["scratchpad"]["triage_reasoning"] == "A plan"
    assert result["scratchpad"]["triage_actions"] == []


# ==============================================================================
# Data Injection / Blind Triage Tests
# ==============================================================================

def test_triage_appends_system_note_for_text_to_process(triage_architect, mock_llm_adapter):
    """
    Test that TriageArchitect appends a system note when text_to_process is in artifacts.

    Bug fixed: When user uploads a file, the content goes to artifacts['text_to_process'].
    Without a system note, the LLM would emit READ_FILE with a guessed filename,
    causing MCP to fail with "File not found".

    The fix appends [SYSTEM NOTE] telling LLM the content is already available.
    """
    uploaded_content = "This is the content of an uploaded file with important information."
    state = {
        "messages": [HumanMessage(content="Analyze the uploaded document")],
        "artifacts": {"text_to_process": uploaded_content}
    }

    expected_plan = {
        "reasoning": "Content already in artifacts, no READ_FILE needed",
        "actions": []  # Should NOT emit READ_FILE
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - verify the LLM was called with the system note
    call_args = mock_llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    # Find the message with the system note
    system_note_found = False
    for msg in messages:
        if hasattr(msg, 'content') and "[SYSTEM NOTE:" in msg.content:
            system_note_found = True
            # Verify key content of the note
            assert "uploaded a document" in msg.content
            assert str(len(uploaded_content)) in msg.content  # Character count
            assert "ALREADY AVAILABLE" in msg.content
            assert "Do NOT emit READ_FILE or RESEARCH" in msg.content
            break

    assert system_note_found, "System note for text_to_process should be appended to messages"


def test_triage_no_system_note_without_text_to_process(triage_architect, mock_llm_adapter):
    """
    Test that no system note is appended when text_to_process is NOT in artifacts.
    """
    state = {
        "messages": [HumanMessage(content="Hello, how are you?")],
        "artifacts": {}  # No text_to_process
    }

    expected_plan = {
        "reasoning": "Simple greeting",
        "actions": []
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - verify no system note was added
    call_args = mock_llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    for msg in messages:
        if hasattr(msg, 'content'):
            assert "[SYSTEM NOTE:" not in msg.content, "No system note should be added without text_to_process"


def test_triage_appends_system_note_for_uploaded_image(triage_architect, mock_llm_adapter):
    """
    Test that TriageArchitect appends a system note when uploaded_image.png is in artifacts.

    This tests the pre-existing image handling (which served as the pattern for text_to_process).
    """
    state = {
        "messages": [HumanMessage(content="Describe this image")],
        "artifacts": {"uploaded_image.png": b"fake image bytes"}
    }

    expected_plan = {
        "reasoning": "Image analysis needed",
        "actions": []
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - verify the image system note was appended
    call_args = mock_llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    system_note_found = False
    for msg in messages:
        if hasattr(msg, 'content') and "[SYSTEM NOTE:" in msg.content:
            system_note_found = True
            assert "uploaded an image" in msg.content
            assert "Do not ask for the image" in msg.content
            break

    assert system_note_found, "System note for uploaded image should be appended"


def test_triage_both_text_and_image_get_system_notes(triage_architect, mock_llm_adapter):
    """
    Test that both text and image system notes are appended when both are present.
    """
    state = {
        "messages": [HumanMessage(content="Compare the document with the image")],
        "artifacts": {
            "text_to_process": "Document content here",
            "uploaded_image.png": b"fake image bytes"
        }
    }

    expected_plan = {
        "reasoning": "Multi-modal analysis",
        "actions": []
    }

    mock_llm_adapter.invoke.return_value = {
        "json_response": expected_plan
    }

    # Act
    result = triage_architect.execute(state)

    # Assert - verify both notes are appended (in sequence)
    call_args = mock_llm_adapter.invoke.call_args[0][0]
    messages = call_args.messages

    text_note_found = False
    image_note_found = False

    for msg in messages:
        if hasattr(msg, 'content'):
            if "uploaded a document" in msg.content:
                text_note_found = True
            if "uploaded an image" in msg.content:
                image_note_found = True

    assert text_note_found, "Text system note should be appended"
    assert image_note_found, "Image system note should be appended"
