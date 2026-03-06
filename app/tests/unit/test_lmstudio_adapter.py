
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


# =============================================================================
# Per-Tool Schema Isolation (oneOf)
# =============================================================================

class TestBuildToolCallSchemaOneOf:
    """Verify _build_tool_call_schema produces per-tool oneOf variants."""

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_multi_tool_schema_uses_oneOf(self, mock_openai_client, mock_model_config):
        """Multi-tool schema should use oneOf inside actions array items."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class create_directory(BaseModel):
            path: str = Field(description="Directory path")

        class run_command(BaseModel):
            command: str = Field(description="Shell command")

        schema = adapter._build_tool_call_schema([create_directory, run_command])
        actions_prop = schema["properties"]["actions"]
        assert actions_prop["type"] == "array"
        assert actions_prop["minItems"] == 1
        items = actions_prop["items"]

        assert "oneOf" in items, f"Expected oneOf in items, got: {items.keys()}"
        # 2 tools + DONE = 3 variants
        assert len(items["oneOf"]) == 3

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_each_variant_has_only_own_params(self, mock_openai_client, mock_model_config):
        """create_directory variant should have path but NOT command."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class create_directory(BaseModel):
            path: str = Field(description="Directory path")

        class run_command(BaseModel):
            command: str = Field(description="Shell command")

        schema = adapter._build_tool_call_schema([create_directory, run_command])
        variants = schema["properties"]["actions"]["items"]["oneOf"]

        # Find create_directory variant
        cd_variant = next(v for v in variants if v["properties"]["tool_name"].get("const") == "create_directory")
        rc_variant = next(v for v in variants if v["properties"]["tool_name"].get("const") == "run_command")

        assert "path" in cd_variant["properties"]
        assert "command" not in cd_variant["properties"]
        assert "command" in rc_variant["properties"]
        assert "path" not in rc_variant["properties"]

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_variants_have_additionalProperties_false(self, mock_openai_client, mock_model_config):
        """Each variant should block extra fields."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class read_file(BaseModel):
            path: str = Field(description="File path")

        schema = adapter._build_tool_call_schema([read_file, read_file])
        for variant in schema["properties"]["actions"]["items"]["oneOf"]:
            assert variant.get("additionalProperties") is False

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_single_tool_has_no_DONE_variant(self, mock_openai_client, mock_model_config):
        """Single-tool schema should not include DONE."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class Route(BaseModel):
            next_specialist: str = Field(description="Next specialist")

        schema = adapter._build_tool_call_schema([Route])
        variants = schema["properties"]["actions"]["items"]["oneOf"]

        assert len(variants) == 1
        assert variants[0]["properties"]["tool_name"]["const"] == "Route"

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_DONE_variant_has_only_tool_name(self, mock_openai_client, mock_model_config):
        """DONE variant should have tool_name and nothing else."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        schema = adapter._build_tool_call_schema([read_file, move_file])
        done_variant = next(v for v in schema["properties"]["actions"]["items"]["oneOf"]
                          if v["properties"]["tool_name"].get("const") == "DONE")

        assert set(done_variant["properties"].keys()) == {"tool_name"}
        assert done_variant["required"] == ["tool_name"]

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_schema_required_has_actions_not_action(self, mock_openai_client, mock_model_config):
        """Schema should require 'actions' (array), not 'action' (singular)."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config,
            base_url=MOCK_BASE_URL,
            system_prompt="Test"
        )
        from pydantic import Field

        class read_file(BaseModel):
            path: str = Field(description="File path")

        schema = adapter._build_tool_call_schema([read_file, read_file])
        assert "actions" in schema["required"]
        assert "action" not in schema["required"]
        assert "actions" in schema["properties"]
        assert "action" not in schema["properties"]


# =============================================================================
# Parse Completion: Actions Array (Phase 0.9)
# =============================================================================

class TestParseCompletionActionsArray:
    """Verify _parse_completion handles the actions array format for concurrent dispatch."""

    def _make_completion(self, json_content: str):
        """Helper: build a mock completion with JSON content."""
        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock()]
        mock_completion.choices[0].message.content = json_content
        mock_completion.choices[0].message.tool_calls = None
        return mock_completion

    def _make_request_and_kwargs(self, adapter, tool_classes):
        """Helper: build request + api_kwargs that trigger the JSON schema path."""
        import time
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="test")],
            tools=tool_classes,
        )
        api_kwargs = adapter._build_request_kwargs(request)
        return request, api_kwargs

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_single_action_in_array(self, mock_openai_client, mock_model_config):
        """Single action in array produces one tool_call."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "Need to read file",
            "actions": [{"tool_name": "read_file", "path": "/tmp/a.txt"}]
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read_file"
        assert result["tool_calls"][0]["args"] == {"path": "/tmp/a.txt"}

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_multiple_actions_in_array(self, mock_openai_client, mock_model_config):
        """Multiple actions produce multiple tool_calls for concurrent dispatch."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "Read both files concurrently",
            "actions": [
                {"tool_name": "read_file", "path": "/tmp/a.txt"},
                {"tool_name": "read_file", "path": "/tmp/b.txt"},
            ]
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert len(result["tool_calls"]) == 2
        assert result["tool_calls"][0]["name"] == "read_file"
        assert result["tool_calls"][0]["args"] == {"path": "/tmp/a.txt"}
        assert result["tool_calls"][1]["args"] == {"path": "/tmp/b.txt"}
        # Each should have a unique ID
        assert result["tool_calls"][0]["id"] != result["tool_calls"][1]["id"]

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_done_in_array(self, mock_openai_client, mock_model_config):
        """DONE action in array returns text_response."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "Task complete",
            "actions": [{"tool_name": "DONE"}],
            "final_response": "All files sorted successfully."
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert "text_response" in result
        assert result["text_response"] == "All files sorted successfully."
        assert "tool_calls" not in result

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_mixed_done_and_tools_done_wins(self, mock_openai_client, mock_model_config):
        """DONE takes priority over concurrent tool calls in mixed array."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "Done now",
            "actions": [
                {"tool_name": "read_file", "path": "/tmp/a.txt"},
                {"tool_name": "DONE"},
            ],
            "final_response": "Done."
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert "text_response" in result
        assert result["text_response"] == "Done."
        assert "tool_calls" not in result

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_fallback_to_singular_action(self, mock_openai_client, mock_model_config):
        """Old singular 'action' format still works as backward compat fallback."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "Reading file",
            "action": {"tool_name": "read_file", "path": "/tmp/a.txt"}
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert "tool_calls" in result
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "read_file"

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_reasoning_threaded_as_text_response(self, mock_openai_client, mock_model_config):
        """Reasoning field should be passed through as text_response for thought capture."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, move_file])
        completion = self._make_completion(json.dumps({
            "reasoning": "I need to read both files to understand their contents",
            "actions": [{"tool_name": "read_file", "path": "/tmp/a.txt"}]
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert result["text_response"] == "I need to read both files to understand their contents"

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_param_stripping_per_action(self, mock_openai_client, mock_model_config):
        """Param stripping is applied independently to each action in the array."""
        adapter = LMStudioAdapter(
            model_config=mock_model_config, base_url=MOCK_BASE_URL, system_prompt=""
        )
        from pydantic import Field
        import time

        class read_file(BaseModel):
            path: str = Field(description="File path")

        class create_directory(BaseModel):
            path: str = Field(description="Dir path")

        request, api_kwargs = self._make_request_and_kwargs(adapter, [read_file, create_directory])
        # Model hallucinated 'command' param on read_file and 'query' on create_directory
        completion = self._make_completion(json.dumps({
            "reasoning": "Read and create",
            "actions": [
                {"tool_name": "read_file", "path": "/tmp/a.txt", "command": "cat"},
                {"tool_name": "create_directory", "path": "/tmp/new", "query": "test"},
            ]
        }))

        result = adapter._parse_completion(completion, request, api_kwargs, time.perf_counter())

        assert len(result["tool_calls"]) == 2
        # read_file should only have 'path', not 'command'
        assert result["tool_calls"][0]["args"] == {"path": "/tmp/a.txt"}
        # create_directory should only have 'path', not 'query'
        assert result["tool_calls"][1]["args"] == {"path": "/tmp/new"}


# =============================================================================
# Parser Param Filtering
# =============================================================================

class TestParserParamFiltering:
    """Verify _parse_completion strips irrelevant params from tool calls."""

    def test_get_known_params_for_tool_found(self):
        """Should return field names for matching tool."""
        from pydantic import Field

        class create_directory(BaseModel):
            path: str = Field(description="Dir path")

        result = LMStudioAdapter._get_known_params_for_tool("create_directory", [create_directory])
        assert result == {"path"}

    def test_get_known_params_for_tool_not_found(self):
        """Should return None for unknown tool (permissive fallback)."""
        result = LMStudioAdapter._get_known_params_for_tool("unknown_tool", [])
        assert result is None

    def test_get_known_params_multi_field_tool(self):
        """Should return all field names for a multi-field tool."""
        from pydantic import Field

        class move_file(BaseModel):
            source: str = Field(description="Source")
            destination: str = Field(description="Dest")

        result = LMStudioAdapter._get_known_params_for_tool("move_file", [move_file])
        assert result == {"source", "destination"}


# =============================================================================
# Issue #219: Harmony Token Stripping & Schema Enforcement Skip
# =============================================================================

class TestHarmonyTokenStripping:
    """Tests for _strip_harmony_tokens and skip_schema_enforcement (#219).

    gpt-oss models use the Harmony response format with special tokens
    (<|channel|>, <|constrain|>, <|message|>, etc.) that are incompatible
    with llama.cpp's GBNF grammar-constrained decoding. When
    skip_schema_enforcement is True, we skip response_format and strip
    Harmony tokens before JSON parsing.
    """

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_strip_harmony_tokens_from_structured_output(self, mock_openai):
        """Harmony-wrapped SystemPlan JSON should parse correctly after stripping."""
        adapter = LMStudioAdapter(
            model_config={"api_identifier": "gpt-oss-20b", "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="You are a systems architect."
        )

        # Simulate Harmony-wrapped response
        harmony_text = (
            '<|channel|>final <|constrain|>SystemPlan<|message|>'
            '{"plan_summary":"Categorize files.","required_components":[],'
            '"execution_steps":["Read files","Create dirs","Move files"],'
            '"acceptance_criteria":"Each subdirectory contains at least two files."}'
        )
        stripped = adapter._strip_harmony_tokens(harmony_text)

        # Should be parseable as JSON after stripping
        # (robust parser handles leftover channel labels like "final SystemPlan")
        import json
        start = stripped.find('{')
        json_str = stripped[start:]
        parsed = json.loads(json_str)
        assert parsed["plan_summary"] == "Categorize files."
        assert len(parsed["execution_steps"]) == 3

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_strip_harmony_tokens_from_tool_response(self, mock_openai):
        """Harmony-wrapped tool call JSON should parse correctly after stripping."""
        adapter = LMStudioAdapter(
            model_config={"api_identifier": "gpt-oss-20b", "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        harmony_text = (
            '<|start|>assistant<|channel|>final <|constrain|>json<|message|>'
            '{"reasoning":"Need to list files","actions":[{"tool_name":"list_directory","path":"/workspace"}]}'
        )
        stripped = adapter._strip_harmony_tokens(harmony_text)

        import json
        start = stripped.find('{')
        parsed = json.loads(stripped[start:])
        assert parsed["actions"][0]["tool_name"] == "list_directory"

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_strip_preserves_clean_json(self, mock_openai):
        """When no Harmony tokens are present, content passes through unchanged."""
        adapter = LMStudioAdapter(
            model_config={"api_identifier": "qwen3-30b", "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        clean_json = '{"plan_summary":"A plan.","execution_steps":["Step 1"]}'
        stripped = adapter._strip_harmony_tokens(clean_json)
        assert stripped == clean_json

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_skip_schema_enforcement_omits_response_format(self, mock_openai):
        """When skip_schema_enforcement=True, _build_request_kwargs should NOT set response_format."""
        adapter = LMStudioAdapter(
            model_config={
                "api_identifier": "gpt-oss-20b",
                "parameters": {},
                "skip_schema_enforcement": True,
            },
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        assert adapter.skip_schema_enforcement is True

        # Request with output_model_class (SA path)
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Plan something")],
            output_model_class=type("FakeSchema", (BaseModel,), {"__annotations__": {"plan": str}}),
        )
        kwargs = adapter._build_request_kwargs(request)
        assert "response_format" not in kwargs

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_schema_enforcement_default_false(self, mock_openai):
        """skip_schema_enforcement defaults to False when not specified in config."""
        adapter = LMStudioAdapter(
            model_config={"api_identifier": "qwen3-30b", "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert adapter.skip_schema_enforcement is False

    @patch('app.src.llm.lmstudio_adapter.OpenAI')
    def test_skip_schema_enforcement_with_tools_omits_response_format(self, mock_openai):
        """When skip_schema_enforcement=True, tool requests also skip response_format."""
        adapter = LMStudioAdapter(
            model_config={
                "api_identifier": "gpt-oss-20b",
                "parameters": {},
                "skip_schema_enforcement": True,
            },
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        class list_directory(BaseModel):
            path: str

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="List files")],
            tools=[list_directory],
        )
        kwargs = adapter._build_request_kwargs(request)
        assert "response_format" not in kwargs


# --- #235: Per-server authentication token ---

@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_api_key_from_constructor(mock_openai_client):
    """Explicit api_key passed to constructor takes priority."""
    adapter = LMStudioAdapter(
        model_config={"api_identifier": MOCK_MODEL_NAME},
        base_url=MOCK_BASE_URL,
        system_prompt="",
        api_key="my-server-token",
    )
    assert adapter.api_key == "my-server-token"


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_api_key_fallback_to_env(mock_openai_client, monkeypatch):
    """Falls back to LMSTUDIO_API_KEY env var when no explicit key."""
    monkeypatch.setenv("LMSTUDIO_API_KEY", "env-token")
    adapter = LMStudioAdapter(
        model_config={"api_identifier": MOCK_MODEL_NAME},
        base_url=MOCK_BASE_URL,
        system_prompt="",
    )
    assert adapter.api_key == "env-token"


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_api_key_fallback_to_not_needed(mock_openai_client, monkeypatch):
    """Falls back to 'not-needed' when no explicit key and no env var."""
    monkeypatch.delenv("LMSTUDIO_API_KEY", raising=False)
    adapter = LMStudioAdapter(
        model_config={"api_identifier": MOCK_MODEL_NAME},
        base_url=MOCK_BASE_URL,
        system_prompt="",
    )
    assert adapter.api_key == "not-needed"


@patch('app.src.llm.lmstudio_adapter.OpenAI')
def test_from_config_passes_api_key(mock_openai_client):
    """from_config extracts api_key from provider_config and passes it through."""
    provider_config = {
        "api_identifier": MOCK_MODEL_NAME,
        "base_url": MOCK_BASE_URL,
        "api_key": "config-token",
    }
    adapter = LMStudioAdapter.from_config(provider_config, system_prompt="")
    assert adapter.api_key == "config-token"