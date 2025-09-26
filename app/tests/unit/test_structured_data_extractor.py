
import pytest
from unittest.mock import MagicMock, ANY
from pydantic import BaseModel, Field

from app.src.specialists.structured_data_extractor import StructuredDataExtractor
from langchain_core.messages import HumanMessage, AIMessage
from app.src.utils.errors import LLMInvocationError
from app.src.specialists.helpers import create_llm_message

# Define a simple Pydantic schema for testing purposes
class MockUserInfo(BaseModel):
    """A mock model for testing."""
    name: str = Field(..., description="The user's name.")
    email: str = Field(..., description="The user's email.")

@pytest.fixture
def structured_data_extractor(initialized_specialist_factory):
    """Fixture to create an instance of StructuredDataExtractor with a mocked LLM adapter."""
    return initialized_specialist_factory("StructuredDataExtractor")


# Test cases
def test_structured_data_extractor_success(structured_data_extractor):
    """Tests successful data extraction and state update."""
    # Arrange
    mock_llm_response = {
        "tool_calls": [{
            "name": "MockUserInfo",
            "args": {"name": "John Doe", "email": "john.doe@example.com"},
            "id": "call_123"
        }]
    }
    structured_data_extractor.llm_adapter.invoke.return_value = mock_llm_response

    initial_state = {
        "messages": [HumanMessage(content="My name is John Doe and my email is john.doe@example.com")],
        "scratchpad": {
            "extraction_schema": MockUserInfo,
            "target_artifact_name": "user_profile"
        }
    }

    # Act
    result_state = structured_data_extractor._execute_logic(initial_state)

    # Assert
    structured_data_extractor.llm_adapter.invoke.assert_called_once()
    request = structured_data_extractor.llm_adapter.invoke.call_args[0][0]
    assert request.tools == [MockUserInfo]
    assert request.force_tool_call is True

    assert "extracted_data" in result_state
    # The artifact is now a dictionary in the 'extracted_data' key
    assert result_state["extracted_data"]["name"] == "John Doe"
    assert result_state["extracted_data"]["email"] == "john.doe@example.com"
    assert result_state.get("task_is_complete") is True
    assert "Successfully extracted" in result_state["messages"][0].content

def test_structured_data_extractor_missing_scratchpad_input(structured_data_extractor):
    """
    Tests that the specialist handles missing scratchpad inputs gracefully.
    """
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Extract user info.")],
        "scratchpad": {} # Missing schema and target name
    }
 
    # Act
    result_state = structured_data_extractor._execute_logic(initial_state)
 
    # Assert
    structured_data_extractor.llm_adapter.invoke.assert_not_called()
    assert "extracted_data" not in result_state
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "State missing 'extraction_schema' or 'target_artifact_name'" in result_state["messages"][0].content

def test_structured_data_extractor_llm_fails_to_extract(structured_data_extractor):
    """Tests the fallback mechanism when the LLM fails to return a tool call."""
    # Arrange
    # Simulate the LLM returning a text response instead of a tool call
    structured_data_extractor.llm_adapter.invoke.return_value = {"text_response": "I am sorry, I cannot help with that."}

    initial_state = {
        "messages": [HumanMessage(content="Some unparseable text.")],
        "scratchpad": {
            "extraction_schema": MockUserInfo,
            "target_artifact_name": "user_profile"
        }
    }

    # Act
    result_state = structured_data_extractor._execute_logic(initial_state)

    # Assert
    structured_data_extractor.llm_adapter.invoke.assert_called_once()
    assert "extracted_data" not in result_state
    assert isinstance(result_state["messages"][0], AIMessage)
    assert "unable to extract the required 'MockUserInfo' data" in result_state["messages"][0].content

def test_structured_data_extractor_malformed_tool_call_args(structured_data_extractor):
    """Tests that the specialist handles tool calls with arguments that don't match the schema."""
    # Arrange
    mock_llm_response = {
        "tool_calls": [{
            "name": "MockUserInfo",
            "args": {"name": "John Doe"}, # Missing 'email' field
            "id": "call_123"
        }]
    }
    structured_data_extractor.llm_adapter.invoke.return_value = mock_llm_response

    initial_state = {
        "messages": [HumanMessage(content="My name is John Doe.")],
        "scratchpad": {"extraction_schema": MockUserInfo, "target_artifact_name": "user_profile"}
    }

    # Act
    result_state = structured_data_extractor._execute_logic(initial_state)

    # Assert
    assert "extracted_data" not in result_state
    assert "LLM tool call arguments failed Pydantic validation" in result_state["messages"][0].content
    assert "email" in result_state["messages"][0].content # Error message should mention the missing field

def test_structured_data_extractor_handles_llm_invocation_error(structured_data_extractor):
    """Tests that the specialist handles exceptions from the LLM adapter."""
    # Arrange
    structured_data_extractor.llm_adapter.invoke.side_effect = LLMInvocationError("API timeout")

    initial_state = {
        "messages": [HumanMessage(content="Some text.")],
        "scratchpad": {"extraction_schema": MockUserInfo, "target_artifact_name": "user_profile"}
    }

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="API timeout"):
        structured_data_extractor._execute_logic(initial_state)

def test_structured_data_extractor_handles_invalid_schema_in_scratchpad(structured_data_extractor):
    """Tests that the specialist handles an invalid schema object gracefully."""
    # Arrange
    initial_state = {
        "messages": [HumanMessage(content="Some text.")],
        "scratchpad": {
            "extraction_schema": "not-a-pydantic-model",
            "target_artifact_name": "user_profile"
        }
    }

    # Act
    result_state = structured_data_extractor._execute_logic(initial_state)

    # Assert
    structured_data_extractor.llm_adapter.invoke.assert_not_called()
    assert "extracted_data" not in result_state
    assert "Expected a Pydantic model class" in result_state["messages"][0].content
