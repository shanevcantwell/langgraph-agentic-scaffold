import pytest
from unittest.mock import MagicMock, ANY
from pydantic import BaseModel, Field

from app.src.specialists.structured_data_extractor import StructuredDataExtractor
from langchain_core.messages import HumanMessage, AIMessage

# Define a simple Pydantic schema for testing purposes
class MockUserInfo(BaseModel):
    """A mock model for testing."""
    name: str = Field(..., description="The user's name.")
    email: str = Field(..., description="The user's email.")

@pytest.fixture
def structured_data_extractor():
    """Fixture to create an instance of StructuredDataExtractor with a mocked LLM adapter."""
    specialist = StructuredDataExtractor(
        specialist_name="structured_data_extractor",
        specialist_config={}
    )
    specialist.llm_adapter = MagicMock()
    # Mock the create_llm_message helper to return a simple AIMessage
    specialist.create_llm_message = lambda **kwargs: AIMessage(content=kwargs.get("content", ""), name=specialist.specialist_name)
    return specialist


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
    assert request.tool_choice == "MockUserInfo"

    assert "extracted_data" in result_state
    # The artifact is now a dictionary in the 'extracted_data' key
    assert result_state["extracted_data"]["name"] == "John Doe"
    assert result_state["extracted_data"]["email"] == "john.doe@example.com"
    assert result_state["task_is_complete"] is True
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
