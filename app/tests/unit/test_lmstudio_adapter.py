
import json
import pytest
from unittest.mock import patch, MagicMock, call

from app.src.llm.lmstudio_adapter import LMStudioAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from app.src.utils.errors import LLMInvocationError, ProxyError
from langchain_core.messages import HumanMessage
import httpx
from openai import APIConnectionError, PermissionDeniedError
from pydantic import BaseModel

MOCK_MODEL_NAME = "test-model/test-model-GGUF"
MOCK_BASE_URL = "http://fake-lmstudio:1234/v1"

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Mocks environment variables for tests."""
    monkeypatch.setenv("LMSTUDIO_BASE_URL", MOCK_BASE_URL)
    monkeypatch.setenv("LMSTUDIO_SSH_HOST", "fake-host")
    monkeypatch.setenv("LMSTUDIO_SSH_USER", "fake-user")
    monkeypatch.setenv("LMSTUDIO_SSH_KEY_PATH", "/fake/path/id_rsa")

@pytest.fixture
def mock_model_config():
    """Provides a basic model configuration."""
    return {
        "api_identifier": MOCK_MODEL_NAME,
        "parameters": {"temperature": 0.7}
    }

def test_init_fails_on_missing_api_identifier():
    """Tests that initialization fails if 'api_identifier' is missing from the config."""
    with pytest.raises(TypeError, match="argument of type 'NoneType' is not iterable"):
        LMStudioAdapter(model_config={}, base_url=MOCK_BASE_URL, system_prompt="")

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_sends_correct_request(mock_openai_client, mock_model_config):
    """Tests that the invoke method constructs and sends the correct request to the client."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="You are a helpful assistant.")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "LLM response text"

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello, world!")])

    # Act
    result = adapter.invoke(request)

    # Assert
    mock_create.assert_called_once()
    call_args, call_kwargs = mock_create.call_args
    
    # Check messages payload
    sent_messages = call_kwargs['messages']
    assert len(sent_messages) == 2
    assert sent_messages[0]['role'] == 'system'
    assert sent_messages[0]['content'] == 'You are a helpful assistant.'
    assert sent_messages[1]['role'] == 'user'
    assert sent_messages[1]['content'] == 'Hello, world!'

    # Check other parameters
    assert call_kwargs['model'] == MOCK_MODEL_NAME
    assert call_kwargs['temperature'] == 0.7
    assert result.get('text_response') == "LLM response text"

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_handles_json_parsing(mock_openai_client, mock_model_config):
    """Tests that the invoke method correctly parses JSON from a messy response string."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "Here is the JSON: ```json\n{\"key\": \"value\"}\n```"

    class MockSchema(BaseModel): pass
    request = StandardizedLLMRequest(messages=[], output_model_class=MockSchema)

    # Act
    result = adapter.invoke(request)

    # Assert
    assert result.get('json_response') == {"key": "value"}
    assert result.get('text_response') is None

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_raises_llm_invocation_error(mock_openai_client, mock_model_config):
    """Tests that LLMInvocationError is raised when the client call fails."""
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.side_effect = Exception("API call failed")

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])

    # Act & Assert
    with pytest.raises(LLMInvocationError, match="LMStudio API error: API call failed"):
        adapter.invoke(request)

@pytest.mark.parametrize("raised_exception", [
    APIConnectionError(request=MagicMock()),
    PermissionDeniedError("Access Denied", response=MagicMock(), body=None),
    httpx.ProxyError("Proxy connection failed")
])
@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_invoke_raises_proxy_error_on_connection_issues(mock_openai_client, mock_model_config, raised_exception):
    """
    Tests that the LMStudio adapter correctly catches various connection-related
    exceptions and raises a unified ProxyError.
    """
    # Arrange
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.side_effect = raised_exception

    request = StandardizedLLMRequest(messages=[HumanMessage(content="Hello")])

    expected_message = ("A network error occurred, which is often due to a proxy blocking the request. "
                        "Please check your proxy's 'squid.conf' to ensure the destination is whitelisted.")

    # Act & Assert
    with pytest.raises(ProxyError, match=expected_message):
        adapter.invoke(request)


# =============================================================================
# Image Handling Tests (Issue #16)
# =============================================================================

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_image_injection_skips_empty_data(mock_openai_client, mock_model_config):
    """Tests that empty string image_data is treated as 'no image' (skips injection)."""
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="Test")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "Response"

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Describe this image")],
        image_data=""  # Empty string = no image
    )

    result = adapter.invoke(request)

    # Should succeed without image injection
    assert result.get("text_response") == "Response"
    call_kwargs = mock_create.call_args[1]
    user_message = call_kwargs['messages'][1]
    # Content should be plain string, not multimodal list
    assert isinstance(user_message['content'], str)


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_image_injection_rejects_whitespace_only_data(mock_openai_client, mock_model_config):
    """Tests that whitespace-only image data raises ValueError."""
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Describe this image")],
        image_data="   \n\t  "  # Whitespace only
    )

    with pytest.raises(ValueError, match="Image data is empty or whitespace-only"):
        adapter.invoke(request)


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_image_injection_rejects_oversized_image(mock_openai_client, mock_model_config):
    """Tests that oversized image data raises ValueError with helpful message."""
    # Configure a small limit for testing (1MB)
    mock_model_config["max_image_size_mb"] = 1
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

    # Create a 2MB base64 string (exceeds 1MB limit)
    oversized_image = "A" * (2 * 1024 * 1024)

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Describe this image")],
        image_data=oversized_image
    )

    with pytest.raises(ValueError, match="Image data exceeds maximum size"):
        adapter.invoke(request)


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_image_injection_accepts_valid_sized_image(mock_openai_client, mock_model_config):
    """Tests that valid-sized image data passes size check and proceeds to injection."""
    mock_model_config["max_image_size_mb"] = 10
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="Test")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "Image description"

    # Valid base64 image data (small, under limit)
    valid_image = "iVBORw0KGgoAAAANSUhEUg=="

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Describe this image")],
        image_data=valid_image
    )

    result = adapter.invoke(request)

    # Should succeed and return response
    assert result.get("text_response") == "Image description"
    # Verify image was injected into the request
    call_kwargs = mock_create.call_args[1]
    user_message = call_kwargs['messages'][1]
    assert isinstance(user_message['content'], list)
    assert user_message['content'][1]['type'] == 'image_url'


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_image_injection_rejects_empty_message_content(mock_openai_client, mock_model_config):
    """Tests that empty message content raises ValueError when injecting image."""
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="")],  # Empty message content
        image_data="iVBORw0KGgoAAAANSUhEUg=="
    )

    with pytest.raises(ValueError, match="Cannot inject image into message with empty content"):
        adapter.invoke(request)


# =============================================================================
# Issue #123: Structured Output Validation and JSON Extraction
# =============================================================================

class StructuredOutputSchema(BaseModel):
    """Schema for testing structured output (named to avoid pytest collection)."""
    name: str
    value: int


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_structured_output_raises_on_invalid_json(mock_openai_client, mock_model_config):
    """
    Issue #123: When output_model_class is set, adapter should raise error
    if model fails to produce valid JSON (not silently return empty).
    """
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "I cannot generate valid JSON for this request."

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Generate structured output")],
        output_model_class=StructuredOutputSchema
    )

    # Adapter wraps internal ValueError in LLMInvocationError
    with pytest.raises(LLMInvocationError, match="failed to produce valid.*structured output"):
        adapter.invoke(request)


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_text_response_extracts_json_when_present(mock_openai_client, mock_model_config):
    """
    Issue #123: When NO output_model_class is set (text mode), adapter should
    still try to extract JSON from the response if present.
    """
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    # Model returns text that happens to contain JSON
    mock_create.return_value.choices[0].message.content = 'Here is the result:\n```json\n{"status": "complete", "count": 5}\n```'

    # NO output_model_class - plain text request
    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Evaluate the task")]
    )

    result = adapter.invoke(request)

    # Should have BOTH json_response (extracted) and text_response (original)
    assert result.get("json_response") == {"status": "complete", "count": 5}
    assert "Here is the result" in result.get("text_response", "")


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_text_response_no_json_returns_text_only(mock_openai_client, mock_model_config):
    """
    Issue #123: When NO output_model_class is set and response has no JSON,
    adapter should return text_response only (no empty json_response).
    """
    adapter = LMStudioAdapter(model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt="")
    mock_create = mock_openai_client.return_value.chat.completions.create
    mock_create.return_value.choices[0].message.tool_calls = None
    mock_create.return_value.choices[0].message.content = "This is a plain text response with no JSON."

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Just chat")]
    )

    result = adapter.invoke(request)

    # Should have text_response only
    assert result.get("text_response") == "This is a plain text response with no JSON."
    assert result.get("json_response") is None


# =============================================================================
# $ref Resolution Tests (LM Studio doesn't support $defs)
# =============================================================================

class TestResolveSchemaRefs:
    """Tests for LMStudioAdapter._resolve_schema_refs — inlines $defs/$ref."""

    def test_no_refs_unchanged(self):
        """Schema without $ref passes through unchanged."""
        node = {"type": "string", "description": "A simple param"}
        result = LMStudioAdapter._resolve_schema_refs(node, {})
        assert result == node

    def test_direct_ref_resolved(self):
        """A bare $ref node is replaced with the definition."""
        defs = {
            "Foo": {"type": "object", "properties": {"x": {"type": "integer"}}}
        }
        node = {"$ref": "#/$defs/Foo"}
        result = LMStudioAdapter._resolve_schema_refs(node, defs)
        assert result == {"type": "object", "properties": {"x": {"type": "integer"}}}
        assert "$ref" not in str(result)

    def test_ref_in_items_resolved(self):
        """$ref inside array items is resolved (the ParallelCall pattern)."""
        defs = {
            "ParallelCall": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"}
                },
                "required": ["tool"]
            }
        }
        node = {
            "type": "array",
            "items": {"$ref": "#/$defs/ParallelCall"},
            "description": "List of calls"
        }
        result = LMStudioAdapter._resolve_schema_refs(node, defs)
        assert result["items"]["type"] == "object"
        assert result["items"]["properties"]["tool"]["type"] == "string"
        assert "$ref" not in json.dumps(result)

    def test_nested_refs_resolved_recursively(self):
        """Refs within refs are resolved recursively."""
        defs = {
            "Inner": {"type": "string", "description": "inner"},
            "Outer": {
                "type": "object",
                "properties": {"nested": {"$ref": "#/$defs/Inner"}}
            }
        }
        node = {"$ref": "#/$defs/Outer"}
        result = LMStudioAdapter._resolve_schema_refs(node, defs)
        assert result["properties"]["nested"]["type"] == "string"
        assert "$ref" not in json.dumps(result)

    def test_list_elements_resolved(self):
        """$ref inside a list (e.g., anyOf) is resolved."""
        defs = {"Foo": {"type": "integer"}}
        node = [{"$ref": "#/$defs/Foo"}, {"type": "string"}]
        result = LMStudioAdapter._resolve_schema_refs(node, defs)
        assert result == [{"type": "integer"}, {"type": "string"}]

    def test_missing_def_left_as_is(self):
        """$ref pointing to a missing definition is left unchanged."""
        node = {"$ref": "#/$defs/NonExistent"}
        result = LMStudioAdapter._resolve_schema_refs(node, {})
        assert result == {"$ref": "#/$defs/NonExistent"}


class TestBuildToolCallSchemaRefFree:
    """Verify _build_tool_call_schema produces $ref-free output for LM Studio."""

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_nested_model_schema_has_no_refs(self, mock_openai_client, mock_model_config):
        """_build_tool_call_schema must produce $ref/$defs-free output for nested Pydantic models."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )

        # Create a tool schema with nested Pydantic model (generates $ref/$defs)
        from pydantic import BaseModel, Field

        class InnerItem(BaseModel):
            name: str = Field(description="Item name")
            value: int = Field(description="Item value")

        class tool_with_nested(BaseModel):
            """A tool with nested model parameters."""
            items: list[InnerItem] = Field(description="List of items")

        schema = adapter._build_tool_call_schema([tool_with_nested])
        schema_json = json.dumps(schema)

        assert "$ref" not in schema_json, f"$ref found in schema: {schema_json}"
        assert "$defs" not in schema_json, f"$defs found in schema: {schema_json}"