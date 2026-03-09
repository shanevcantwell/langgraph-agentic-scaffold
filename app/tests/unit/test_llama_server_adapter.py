"""Tests for LlamaServerAdapter — llama-server protocol quirks (#253, #255)."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pydantic import BaseModel, Field

from app.src.llm.llama_server_adapter import LlamaServerAdapter
from app.src.llm.adapter import StandardizedLLMRequest
from langchain_core.messages import HumanMessage

MOCK_MODEL_NAME = "qwen3.5-coder-32b"
MOCK_BASE_URL = "http://fake-llama-server:8080/v1"


# =============================================================================
# Construction
# =============================================================================


class TestConstruction:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_inherits_from_local_inference_adapter(self, mock_openai):
        """LlamaServerAdapter is a LocalInferenceAdapter, NOT LMStudioAdapter."""
        from app.src.llm.local_inference_adapter import LocalInferenceAdapter
        from app.src.llm.lmstudio_adapter import LMStudioAdapter
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert isinstance(adapter, LocalInferenceAdapter)
        assert not isinstance(adapter, LMStudioAdapter)

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_schema_enforcement_enabled_by_default(self, mock_openai):
        """LlamaServerAdapter does NOT skip schema enforcement (#255)."""
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert adapter.skip_schema_enforcement is False

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_respects_explicit_skip_schema(self, mock_openai):
        """Config can explicitly skip schema enforcement if needed."""
        adapter = LlamaServerAdapter(
            model_config={
                "api_identifier": MOCK_MODEL_NAME,
                "parameters": {},
                "skip_schema_enforcement": True,
            },
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert adapter.skip_schema_enforcement is True


# =============================================================================
# Schema enforcement enabled (#255 — llama-server is GBNF reference impl)
# =============================================================================


class TestSchemaEnforcement:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_response_format_with_tools(self, mock_openai):
        """Tool requests SHOULD include response_format (grammar enforcement ON)."""
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        class read_file(BaseModel):
            path: str = Field(description="File path")

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="List files")],
            tools=[read_file],
        )
        kwargs = adapter._build_request_kwargs(request)
        assert "response_format" in kwargs
        assert kwargs["response_format"]["type"] == "json_schema"

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_response_format_with_output_model(self, mock_openai):
        """Structured output requests SHOULD include response_format."""
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        class FakeSchema(BaseModel):
            plan: str

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Plan something")],
            output_model_class=FakeSchema,
        )
        kwargs = adapter._build_request_kwargs(request)
        assert "response_format" in kwargs
        assert kwargs["response_format"]["type"] == "json_schema"


# =============================================================================
# $ref inlining
# =============================================================================


class TestRefInlining:
    def test_refs_resolved_by_inline_schema_refs(self):
        """inline_schema_refs() from server_quirks resolves $ref pointers.

        llama-server doesn't support JSON Schema $defs/$ref. The pooled path
        applies ref inlining via ServerQuirks. This test validates the shared
        inline_schema_refs() function directly.
        """
        from app.src.llm.server_quirks import inline_schema_refs

        class InnerItem(BaseModel):
            name: str = Field(description="Item name")
            value: int = Field(description="Item value")

        class tool_with_nested(BaseModel):
            items: list[InnerItem] = Field(description="List of items")

        schema = tool_with_nested.model_json_schema()
        defs = schema.get("$defs", {})

        # Resolve refs in the properties
        resolved = {k: inline_schema_refs(v, defs) for k, v in schema.get("properties", {}).items()}
        resolved_json = json.dumps(resolved)

        assert "$ref" not in resolved_json
        assert "$defs" not in resolved_json
        # Verify the inlined content is correct
        assert "Item name" in resolved_json
        assert "Item value" in resolved_json

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_output_model_class_refs_inlined_in_response_format(self, mock_openai):
        """output_model_class with nested models → response_format has no $ref/$defs (#260).

        This is the bug path: _build_request_kwargs was sending raw Pydantic schemas
        with $defs/$ref to llama-server, which can't resolve them (llama.cpp #8073).
        """
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        class InnerAction(BaseModel):
            action_type: str = Field(description="Type of action")
            target: str = Field(description="Target of action")

        class PlanWithNested(BaseModel):
            reasoning: str = Field(description="Why")
            actions: list[InnerAction] = Field(description="Actions to take")

        # Verify raw schema HAS $defs/$ref (precondition)
        raw_schema = PlanWithNested.model_json_schema()
        raw_json = json.dumps(raw_schema)
        assert "$defs" in raw_json, "Precondition: Pydantic should generate $defs for nested models"
        assert "$ref" in raw_json, "Precondition: Pydantic should generate $ref for nested models"

        # Build request kwargs — should inline refs
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Plan something")],
            output_model_class=PlanWithNested,
        )
        kwargs = adapter._build_request_kwargs(request)

        # Verify the schema sent to the API has no $ref/$defs
        sent_schema = kwargs["response_format"]["json_schema"]["schema"]
        sent_json = json.dumps(sent_schema)
        assert "$ref" not in sent_json, f"$ref found in sent schema: {sent_json}"
        assert "$defs" not in sent_json, f"$defs found in sent schema: {sent_json}"
        # Verify inlined content is present
        assert "Type of action" in sent_json
        assert "Target of action" in sent_json


# =============================================================================
# No thinking mode injection (#255 — use --reasoning-format none launch flag)
# =============================================================================


class TestNoThinkingInjection:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_no_chat_template_kwargs_in_extra_body(self, mock_openai):
        """Request kwargs should NOT include chat_template_kwargs (#255).

        Thinking mode control moved to llama-server launch flag
        (--reasoning-format none) because per-request enable_thinking
        conflicts with assistant message prefill.
        """
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello")],
        )
        kwargs = adapter._build_request_kwargs(request)

        # No extra_body at all, or no chat_template_kwargs in it
        extra_body = kwargs.get("extra_body", {})
        assert "chat_template_kwargs" not in extra_body

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_extra_body_preserves_user_params(self, mock_openai):
        """User-specified extra_body params (e.g., top_k) still pass through."""
        adapter = LlamaServerAdapter(
            model_config={
                "api_identifier": MOCK_MODEL_NAME,
                "parameters": {"top_k": 40},
            },
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello")],
        )
        kwargs = adapter._build_request_kwargs(request)

        assert "extra_body" in kwargs
        assert kwargs["extra_body"]["top_k"] == 40
        assert "chat_template_kwargs" not in kwargs["extra_body"]


# =============================================================================
# from_config
# =============================================================================


class TestFromConfig:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_from_config_creates_adapter(self, mock_openai):
        """from_config should create a working LlamaServerAdapter."""
        provider_config = {
            "api_identifier": MOCK_MODEL_NAME,
            "base_url": MOCK_BASE_URL,
            "api_key": "test-key",
        }
        adapter = LlamaServerAdapter.from_config(provider_config, system_prompt="test")
        assert adapter.skip_schema_enforcement is False
        assert adapter.api_key == "test-key"
