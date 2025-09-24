# Audit Date: Sept 23, 2025
# app/tests/unit/test_adapter_contracts.py
import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel

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
def test_adapter_robust_parsing_contract(malformed_response, expected_json):
    """
    This contract test verifies that an adapter can robustly parse JSON
    from a malformed text response when a schema is requested.
    """
    # This test uses LMStudioAdapter as the concrete implementation to test against.
    # As other adapters are added, they can be tested here as well.
    adapter = LMStudioAdapter(model_config={"api_identifier": "test-model"}, base_url="http://localhost:1234", system_prompt="")

    # Mock the underlying client call to return the malformed string
    with patch.object(adapter.client.chat.completions, 'create', new_callable=MagicMock) as mock_create:
        mock_create.return_value.choices[0].message.content = malformed_response
        mock_create.return_value.choices[0].message.tool_calls = None

        request = StandardizedLLMRequest(messages=[], output_model_class=MockOutputSchema)
        result = adapter.invoke(request)

        assert "json_response" in result, "Adapter must return a 'json_response' key for schema requests."
        assert result["json_response"] == expected_json, "Adapter failed to correctly parse the malformed JSON."