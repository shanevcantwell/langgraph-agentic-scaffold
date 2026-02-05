# app/tests/unit/test_gemini_adapter.py
"""
Unit tests for GeminiAdapter proxy error handling.

These tests verify that the adapter correctly converts connection errors
into ProxyError exceptions with helpful messages.
"""
import pytest

from unittest.mock import patch, MagicMock

from app.src.llm.gemini_adapter import GeminiAdapter, ProxyError
from app.src.llm.adapter import StandardizedLLMRequest


@pytest.fixture
def mock_gemini_adapter():
    """Fixture to create a GeminiAdapter with a mocked client."""
    with patch('google.genai.Client') as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        adapter = GeminiAdapter(
            model_config={"api_identifier": "gemini-test"},
            api_key="fake-key",
            system_prompt="test prompt"
        )
        yield adapter, mock_client.models.generate_content


@pytest.mark.parametrize("raised_exception, expected_log_message", [
    (
        Exception("RetryError: Deadline Exceeded"),
        "A network error occurred, which is often due to a proxy blocking the request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    ),
    (
        Exception("Some generic proxy error happened"),
        "A proxy error occurred, likely due to a blocked request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    ),
    (
        Exception("<html><body>Access Denied</body></html>"),
        "A proxy error occurred, likely due to a blocked request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    ),
    (
        Exception("Connection refused to host"),
        "A network error occurred, which is often due to a proxy blocking the request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    )
])
def test_invoke_raises_proxy_error_on_connection_issues(mock_gemini_adapter, raised_exception, expected_log_message):
    """
    Tests that the Gemini adapter correctly catches various connection-related
    exceptions and raises a unified ProxyError.
    """
    # Arrange
    adapter, mock_generate_content = mock_gemini_adapter
    mock_generate_content.side_effect = raised_exception
    request = StandardizedLLMRequest(messages=[])

    # Act & Assert
    with pytest.raises(ProxyError, match=expected_log_message):
        adapter.invoke(request)


# =============================================================================
# Issue #123: Structured Output Validation and JSON Extraction
# =============================================================================

from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from app.src.utils.errors import LLMInvocationError


class StructuredOutputSchema(BaseModel):
    """Schema for testing structured output (named to avoid pytest collection)."""
    name: str
    value: int


def test_structured_output_raises_on_invalid_json(mock_gemini_adapter):
    """
    Issue #123: When output_model_class is set, adapter should raise error
    if model fails to produce valid JSON (not silently return empty).
    """
    adapter, mock_generate_content = mock_gemini_adapter

    # Mock response with non-JSON text
    mock_response = MagicMock()
    mock_response.text = "I cannot generate valid JSON for this request."
    mock_generate_content.return_value = mock_response

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Generate structured output")],
        output_model_class=StructuredOutputSchema
    )

    # Adapter wraps internal ValueError in LLMInvocationError
    with pytest.raises(LLMInvocationError, match="failed to produce valid.*structured output"):
        adapter.invoke(request)


def test_text_response_extracts_json_when_present(mock_gemini_adapter):
    """
    Issue #123: When NO output_model_class is set (text mode), adapter should
    still try to extract JSON from the response if present.
    """
    adapter, mock_generate_content = mock_gemini_adapter

    # Mock response with embedded JSON
    mock_response = MagicMock()
    mock_response.text = 'Here is the result:\n```json\n{"status": "complete", "count": 5}\n```'
    mock_generate_content.return_value = mock_response

    # NO output_model_class - plain text request
    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Evaluate the task")]
    )

    result = adapter.invoke(request)

    # Should have BOTH json_response (extracted) and text_response (original)
    assert result.get("json_response") == {"status": "complete", "count": 5}
    assert "Here is the result" in result.get("text_response", "")


def test_text_response_no_json_returns_text_only(mock_gemini_adapter):
    """
    Issue #123: When NO output_model_class is set and response has no JSON,
    adapter should return text_response only (no empty json_response).
    """
    adapter, mock_generate_content = mock_gemini_adapter

    # Mock plain text response
    mock_response = MagicMock()
    mock_response.text = "This is a plain text response with no JSON."
    mock_generate_content.return_value = mock_response

    request = StandardizedLLMRequest(
        messages=[HumanMessage(content="Just chat")]
    )

    result = adapter.invoke(request)

    # Should have text_response only
    assert result.get("text_response") == "This is a plain text response with no JSON."
    assert result.get("json_response") is None
