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
