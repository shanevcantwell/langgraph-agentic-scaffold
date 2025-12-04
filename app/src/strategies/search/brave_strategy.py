"""
Brave Search API strategy implementation.

Brave Search offers:
- 2,000 free requests/month
- No rate limiting on free tier (within quota)
- High-quality results from 30B+ page index

Requires BRAVE_SEARCH_API_KEY environment variable or passed via extra_params.

API docs: https://api-dashboard.search.brave.com/app/documentation/web-search/get-started
"""
import logging
import os
from typing import List, Dict, Any, Optional

import requests

from .base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)


class BraveSearchStrategy(BaseSearchStrategy):
    """
    Search strategy using the Brave Search API.

    Requires an API key from https://brave.com/search/api/
    Free tier: 2,000 requests/month
    """

    API_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    DEFAULT_TIMEOUT = 10  # seconds

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Brave Search strategy.

        Args:
            api_key: Brave Search API key. If not provided, reads from
                     BRAVE_SEARCH_API_KEY environment variable.
        """
        self.api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY")

    def execute(self, request: SearchRequest) -> List[Dict[str, str]]:
        """
        Execute a web search using Brave Search API.

        Args:
            request: SearchRequest with query and max_results

        Returns:
            List of search results with title, url, snippet keys
        """
        query = request.query
        max_results = request.max_results

        # Allow API key override via extra_params
        api_key = request.extra_params.get("api_key", self.api_key)

        if not api_key:
            logger.error("Brave Search API key not configured")
            return [{
                "title": "Configuration Error",
                "url": "",
                "snippet": (
                    "Brave Search API key not configured. "
                    "Set BRAVE_SEARCH_API_KEY environment variable or pass api_key in extra_params."
                )
            }]

        logger.info(f"BraveSearchStrategy executing search for: '{query}'")

        try:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key
            }

            params = {
                "q": query,
                "count": max_results
            }

            response = requests.get(
                self.API_ENDPOINT,
                headers=headers,
                params=params,
                timeout=self.DEFAULT_TIMEOUT
            )

            # Check for rate limiting or quota exceeded
            if response.status_code == 429:
                logger.warning("Brave Search rate limited (429)")
                return [{
                    "title": "Rate Limited",
                    "url": "",
                    "snippet": "Brave Search API rate limit exceeded. Please try again later."
                }]

            if response.status_code == 401:
                logger.error("Brave Search API key invalid or expired")
                return [{
                    "title": "Authentication Error",
                    "url": "",
                    "snippet": "Brave Search API key is invalid or expired."
                }]

            if response.status_code == 422:
                logger.warning(f"Brave Search quota exceeded")
                return [{
                    "title": "Quota Exceeded",
                    "url": "",
                    "snippet": "Brave Search monthly quota exceeded. Upgrade plan or wait for reset."
                }]

            response.raise_for_status()

            data = response.json()

            # Extract web results
            web_results = data.get("web", {}).get("results", [])

            if not web_results:
                return [{
                    "title": "No Results",
                    "url": "",
                    "snippet": f"No results found for query: {query}"
                }]

            results = []
            for r in web_results[:max_results]:
                results.append({
                    "title": r.get("title", "No Title"),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", "No description available.")
                })

            logger.info(f"BraveSearchStrategy returned {len(results)} results")
            return results

        except requests.exceptions.Timeout:
            logger.error("Brave Search request timed out")
            return [{
                "title": "Timeout Error",
                "url": "",
                "snippet": f"Search request timed out after {self.DEFAULT_TIMEOUT}s"
            }]

        except requests.exceptions.RequestException as e:
            logger.error(f"Brave Search request failed: {e}")
            return [{
                "title": "Search Error",
                "url": "",
                "snippet": f"Search request failed: {str(e)}"
            }]

        except Exception as e:
            logger.error(f"Brave Search unexpected error: {e}")
            return [{
                "title": "Search Error",
                "url": "",
                "snippet": f"An unexpected error occurred: {str(e)}"
            }]
