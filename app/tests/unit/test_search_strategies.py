# app/tests/unit/test_search_strategies.py
"""
Unit tests for search strategies.

Tests cover:
- BraveSearchStrategy: API interaction, error handling
- FallbackSearchStrategy: Chain behavior, fallback logic
"""
import pytest
from unittest.mock import MagicMock, patch

from app.src.strategies.search import (
    SearchRequest,
    BraveSearchStrategy,
    DuckDuckGoSearchStrategy,
    FallbackSearchStrategy,
)


# =============================================================================
# BraveSearchStrategy Tests
# =============================================================================

class TestBraveSearchStrategy:
    """Tests for BraveSearchStrategy."""

    def test_requires_api_key(self):
        """Strategy returns error when no API key configured."""
        strategy = BraveSearchStrategy(api_key=None)

        # Ensure env var is not set for this test
        with patch.dict('os.environ', {}, clear=True):
            strategy.api_key = None
            request = SearchRequest(query="test")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Configuration Error"
        assert "API key" in results[0]["snippet"]

    def test_api_key_from_extra_params(self):
        """API key can be passed via extra_params."""
        strategy = BraveSearchStrategy(api_key=None)

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "web": {
                    "results": [
                        {"title": "Test", "url": "http://example.com", "description": "Desc"}
                    ]
                }
            }
            mock_get.return_value = mock_response

            request = SearchRequest(
                query="test",
                extra_params={"api_key": "test_key_from_params"}
            )
            results = strategy.execute(request)

        # Should have called API with the provided key
        mock_get.assert_called_once()
        call_headers = mock_get.call_args[1]["headers"]
        assert call_headers["X-Subscription-Token"] == "test_key_from_params"
        assert len(results) == 1
        assert results[0]["title"] == "Test"

    def test_successful_search(self):
        """Successful search returns formatted results."""
        strategy = BraveSearchStrategy(api_key="test_key")

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "web": {
                    "results": [
                        {"title": "Result 1", "url": "http://a.com", "description": "Desc 1"},
                        {"title": "Result 2", "url": "http://b.com", "description": "Desc 2"},
                    ]
                }
            }
            mock_get.return_value = mock_response

            request = SearchRequest(query="python tutorials", max_results=5)
            results = strategy.execute(request)

        assert len(results) == 2
        assert results[0]["title"] == "Result 1"
        assert results[0]["url"] == "http://a.com"
        assert results[0]["snippet"] == "Desc 1"
        assert results[1]["title"] == "Result 2"

    def test_rate_limited_response(self):
        """Returns Rate Limited marker on 429 status."""
        strategy = BraveSearchStrategy(api_key="test_key")

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_get.return_value = mock_response

            request = SearchRequest(query="test")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Rate Limited"

    def test_auth_error_response(self):
        """Returns Auth Error on 401 status."""
        strategy = BraveSearchStrategy(api_key="bad_key")

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_get.return_value = mock_response

            request = SearchRequest(query="test")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Authentication Error"

    def test_quota_exceeded_response(self):
        """Returns Quota Exceeded on 422 status."""
        strategy = BraveSearchStrategy(api_key="test_key")

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 422
            mock_get.return_value = mock_response

            request = SearchRequest(query="test")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Quota Exceeded"

    def test_empty_results(self):
        """Returns No Results marker when search finds nothing."""
        strategy = BraveSearchStrategy(api_key="test_key")

        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"web": {"results": []}}
            mock_get.return_value = mock_response

            request = SearchRequest(query="obscure query xyz123")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "No Results"

    def test_timeout_handling(self):
        """Returns Timeout Error on request timeout."""
        import requests as req_lib
        strategy = BraveSearchStrategy(api_key="test_key")

        with patch('requests.get') as mock_get:
            mock_get.side_effect = req_lib.exceptions.Timeout("Connection timed out")

            request = SearchRequest(query="test")
            results = strategy.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Timeout Error"


# =============================================================================
# FallbackSearchStrategy Tests
# =============================================================================

class TestFallbackSearchStrategy:
    """Tests for FallbackSearchStrategy."""

    def test_requires_at_least_one_strategy(self):
        """Raises error if no strategies provided."""
        with pytest.raises(ValueError, match="At least one"):
            FallbackSearchStrategy([])

    def test_first_strategy_success(self):
        """Returns results from first strategy if successful."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.return_value = [
            {"title": "First Result", "url": "http://a.com", "snippet": "From first"}
        ]
        mock_strategy2 = MagicMock()

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "First Result"
        mock_strategy1.execute.assert_called_once()
        mock_strategy2.execute.assert_not_called()

    def test_fallback_on_rate_limit(self):
        """Falls back to second strategy on rate limit."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.return_value = [
            {"title": "Rate Limited", "url": "", "snippet": "Try again later"}
        ]
        mock_strategy2 = MagicMock()
        mock_strategy2.execute.return_value = [
            {"title": "Fallback Result", "url": "http://b.com", "snippet": "From second"}
        ]

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Fallback Result"
        mock_strategy1.execute.assert_called_once()
        mock_strategy2.execute.assert_called_once()

    def test_fallback_on_exception(self):
        """Falls back to second strategy on exception."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.side_effect = Exception("Connection failed")
        mock_strategy2 = MagicMock()
        mock_strategy2.execute.return_value = [
            {"title": "Fallback Result", "url": "http://b.com", "snippet": "From second"}
        ]

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Fallback Result"

    def test_all_strategies_fail(self):
        """Returns last error when all strategies fail."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.return_value = [
            {"title": "Rate Limited", "url": "", "snippet": "DDG rate limit"}
        ]
        mock_strategy2 = MagicMock()
        mock_strategy2.execute.return_value = [
            {"title": "Quota Exceeded", "url": "", "snippet": "Brave quota"}
        ]

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Quota Exceeded"  # Last error
        assert "Brave quota" in results[0]["snippet"]

    def test_no_results_is_not_retryable(self):
        """'No Results' is not considered a retryable error."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.return_value = [
            {"title": "No Results", "url": "", "snippet": "Nothing found"}
        ]
        mock_strategy2 = MagicMock()

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        # Should NOT fall back - "No Results" means search worked but found nothing
        assert len(results) == 1
        assert results[0]["title"] == "No Results"
        mock_strategy2.execute.assert_not_called()

    def test_multiple_results_not_retryable(self):
        """Multiple results are never considered retryable errors."""
        mock_strategy1 = MagicMock()
        mock_strategy1.execute.return_value = [
            {"title": "Rate Limited", "url": "", "snippet": ""},
            {"title": "Extra", "url": "", "snippet": ""}
        ]
        mock_strategy2 = MagicMock()

        fallback = FallbackSearchStrategy([mock_strategy1, mock_strategy2])
        request = SearchRequest(query="test")
        results = fallback.execute(request)

        # Two results - not an error condition even if title is suspicious
        assert len(results) == 2
        mock_strategy2.execute.assert_not_called()

    def test_add_strategy_append(self):
        """add_strategy appends by default."""
        mock1 = MagicMock()
        mock2 = MagicMock()
        mock3 = MagicMock()

        fallback = FallbackSearchStrategy([mock1])
        fallback.add_strategy(mock2)
        fallback.add_strategy(mock3)

        assert fallback.strategies == [mock1, mock2, mock3]

    def test_add_strategy_with_priority(self):
        """add_strategy can insert at specific index."""
        mock1 = MagicMock()
        mock2 = MagicMock()
        mock3 = MagicMock()

        fallback = FallbackSearchStrategy([mock1, mock3])
        fallback.add_strategy(mock2, priority=1)

        assert fallback.strategies == [mock1, mock2, mock3]


# =============================================================================
# Integration-style Tests (mocked external calls)
# =============================================================================

class TestFallbackIntegration:
    """Integration tests for fallback behavior with real strategy classes."""

    def test_duckduckgo_to_brave_fallback(self):
        """DuckDuckGo rate limit triggers Brave fallback."""
        from duckduckgo_search.exceptions import RatelimitException

        ddg = DuckDuckGoSearchStrategy()
        ddg.INITIAL_BACKOFF_SECONDS = 0.01
        ddg.MAX_RETRIES = 1

        brave = BraveSearchStrategy(api_key="test_key")

        fallback = FallbackSearchStrategy([ddg, brave])

        with patch('duckduckgo_search.DDGS') as mock_ddgs, \
             patch('requests.get') as mock_brave_get:

            # DDG: rate limited
            mock_ddgs_instance = MagicMock()
            mock_ddgs_instance.__enter__ = MagicMock(return_value=mock_ddgs_instance)
            mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
            mock_ddgs_instance.text.side_effect = RatelimitException("429")
            mock_ddgs.return_value = mock_ddgs_instance

            # Brave: success
            mock_brave_response = MagicMock()
            mock_brave_response.status_code = 200
            mock_brave_response.json.return_value = {
                "web": {
                    "results": [
                        {"title": "Brave Result", "url": "http://brave.com", "description": "Found via Brave"}
                    ]
                }
            }
            mock_brave_get.return_value = mock_brave_response

            request = SearchRequest(query="test query")
            results = fallback.execute(request)

        assert len(results) == 1
        assert results[0]["title"] == "Brave Result"
        assert results[0]["snippet"] == "Found via Brave"
