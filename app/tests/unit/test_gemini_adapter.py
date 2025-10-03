# app/tests/unit/test_gemini_adapter.py
import pytest
from unittest.mock import patch, MagicMock
from google.api_core import exceptions as google_exceptions

from app.src.llm.gemini_adapter import GeminiAdapter, ProxyError
from app.src.llm.adapter import StandardizedLLMRequest

@pytest.fixture
def mock_gemini_adapter():
    """Fixture to create a GeminiAdapter with a mocked model."""
    with patch('google.generativeai.GenerativeModel') as mock_model_class:
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        
        adapter = GeminiAdapter(
            model_config={"api_identifier": "gemini-test"},
            api_key="fake-key",
            system_prompt="test prompt"
        )
        yield adapter, mock_model_instance.generate_content

@pytest.mark.parametrize("raised_exception, expected_log_message", [
    (
        google_exceptions.RetryError("Deadline Exceeded", cause=None),
        "A network error occurred, which is often due to a proxy blocking the request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    ),
    (
        Exception("Some generic proxy error happened"),
        "A proxy error occurred, likely due to a blocked request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
    ),
    (
        Exception("<html><body>Access Denied</body></html>"),
        "A proxy error occurred, likely due to a blocked request. Please check your proxy's 'squid.conf' to ensure the destination is whitelisted."
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

    # Verify that the original error was logged
    # (This requires checking the logs, which can be done with caplog fixture if needed)