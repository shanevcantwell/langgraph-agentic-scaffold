# Audit Date: Sept 23, 2025
# app/tests/unit/test_adapter_contracts.py
import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel
import json
from app.src.llm.adapter import StandardizedLLMRequest
from app.src.llm.lmstudio_adapter import LMStudioAdapter
from app.src.llm.gemini_adapter import GeminiAdapter
from app.src.utils.errors import LLMInvocationError

# --- Test Data ---

class MockOutputSchema(BaseModel):
    """A mock schema for testing structured output."""
    key: str
    value: int

# --- Adapter Fixtures ---

@pytest.fixture(params=[LMStudioAdapter, GeminiAdapter])
def adapter_class(request):
    """Fixture to provide different adapter classes to the tests."""
    return request.param

MALFORMED_RESPONSES = [
    pytest.param(
        "Sure, here is the JSON you requested: {\"key\": \"test\", \"value\": 123}",
        {"key": "test", "value": 123},
        id="json_with_leading_text"
    ),
    pytest.param(
        "```json\n{\"key\": \"test\", \"value\": 123}\n```",
        {"key": "test", "value": 123},
        id="json_in_markdown_block"
    ),
    pytest.param(
        "  \n  {\"key\": \"test\", \"value\": 123}  ",
        {"key": "test", "value": 123},
        id="json_with_whitespace"
    ),
    pytest.param(
        "I am unable to provide that. Here is something else: ```\n{\"key\": \"test\", \"value\": 123}\n``` I hope this helps.",
        {"key": "test", "value": 123},
        id="json_in_markdown_surrounded_by_text"
    ),
]

# --- Contract Test ---

@pytest.mark.parametrize("malformed_response, expected_json", MALFORMED_RESPONSES)
def test_adapter_robust_parsing_contract(adapter_class, malformed_response, expected_json):
    """
    This contract test verifies that an adapter can robustly parse JSON
    from a malformed text response when a schema is requested.
    """
    # Arrange
    if adapter_class == LMStudioAdapter:
        adapter = LMStudioAdapter(model_config={"api_identifier": "test-model"}, base_url="http://localhost:1234", system_prompt="")
        # Mock the underlying client call to return the malformed string
        with patch.object(adapter.client.chat.completions, 'create', new_callable=MagicMock) as mock_create:
            mock_create.return_value.choices[0].message.content = malformed_response
            mock_create.return_value.choices[0].message.tool_calls = None
            request = StandardizedLLMRequest(messages=[], output_model_class=MockOutputSchema)
            
            # Act
            result = adapter.invoke(request)
    elif adapter_class == GeminiAdapter:
        adapter = GeminiAdapter(model_config={"api_identifier": "test-model"}, system_prompt="")
        # Mock the underlying client call for Gemini
        with patch.object(adapter.client, 'generate_content', new_callable=MagicMock) as mock_create:
            mock_create.return_value.text = malformed_response
            request = StandardizedLLMRequest(messages=[], output_model_class=MockOutputSchema)

            # Act
            result = adapter.invoke(request)
    else:
        pytest.fail(f"Adapter class {adapter_class.__name__} not handled in this test.")

    # Assert
    assert "json_response" in result, "Adapter must return a 'json_response' key for schema requests."
    assert result["json_response"] == expected_json, f"Adapter {adapter_class.__name__} failed to correctly parse the malformed JSON."
    assert isinstance(result["json_response"], dict), "The parsed JSON should be a dictionary."