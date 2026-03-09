"""Tests for LlamaServerAdapter — llama-server protocol quirks (#253)."""

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
    def test_forces_skip_schema_enforcement(self, mock_openai):
        """LlamaServerAdapter always forces skip_schema_enforcement=True."""
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert adapter.skip_schema_enforcement is True

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_forces_skip_even_when_config_says_false(self, mock_openai):
        """skip_schema_enforcement=False in config is overridden to True."""
        adapter = LlamaServerAdapter(
            model_config={
                "api_identifier": MOCK_MODEL_NAME,
                "parameters": {},
                "skip_schema_enforcement": False,
            },
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )
        assert adapter.skip_schema_enforcement is True

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


# =============================================================================
# Schema enforcement skipped
# =============================================================================


class TestSchemaEnforcement:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_no_response_format_with_tools(self, mock_openai):
        """Tool requests should NOT include response_format (grammar can't handle oneOf)."""
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
        assert "response_format" not in kwargs

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_no_response_format_with_output_model(self, mock_openai):
        """Structured output requests should NOT include response_format."""
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
        assert "response_format" not in kwargs


# =============================================================================
# $ref inlining
# =============================================================================


class TestRefInlining:
    def test_refs_resolved_by_inline_schema_refs(self):
        """inline_schema_refs() from server_quirks resolves $ref pointers.

        LlamaServerAdapter skips schema enforcement entirely (skip_schema_enforcement=True),
        so _resolve_schema_refs is never reached via _build_tool_call_schema in production.
        The pooled path applies ref inlining via ServerQuirks. This test validates the
        shared inline_schema_refs() function directly.
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


# =============================================================================
# Thinking mode disabled
# =============================================================================


class TestThinkingMode:
    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_extra_body_has_thinking_disabled(self, mock_openai):
        """Request kwargs should include chat_template_kwargs to disable thinking."""
        adapter = LlamaServerAdapter(
            model_config={"api_identifier": MOCK_MODEL_NAME, "parameters": {}},
            base_url=MOCK_BASE_URL,
            system_prompt="test"
        )

        request = StandardizedLLMRequest(
            messages=[HumanMessage(content="Hello")],
        )
        kwargs = adapter._build_request_kwargs(request)

        assert "extra_body" in kwargs
        assert kwargs["extra_body"].get("chat_template_kwargs") == {"enable_thinking": False}

    @patch('app.src.llm.local_inference_adapter.OpenAI')
    def test_extra_body_merges_with_existing(self, mock_openai):
        """Thinking mode params should merge with existing extra_body (e.g., top_k)."""
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
        # Both top_k and thinking disable should be present
        assert kwargs["extra_body"]["top_k"] == 40
        assert kwargs["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}


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
        assert adapter.skip_schema_enforcement is True
        assert adapter.api_key == "test-key"
