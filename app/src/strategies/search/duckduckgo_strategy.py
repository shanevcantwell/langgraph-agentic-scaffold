import logging
import time
from typing import List, Dict, Any
from .base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)


class DuckDuckGoSearchStrategy(BaseSearchStrategy):
    """
    Concrete implementation of BaseSearchStrategy using DuckDuckGo.

    Includes retry logic with exponential backoff for rate limiting.
    """

    # Retry configuration
    MAX_RETRIES = 3
    INITIAL_BACKOFF_SECONDS = 2.0
    BACKOFF_MULTIPLIER = 2.0

    def execute(self, request: SearchRequest) -> List[Dict[str, str]]:
        """
        Executes a web search using DuckDuckGo with retry logic.
        """
        query = request.query
        max_results = request.max_results
        logger.info(f"DuckDuckGoSearchStrategy executing search for: '{query}'")

        try:
            # Lazy import to avoid hard dependency if not installed
            from duckduckgo_search import DDGS
            from duckduckgo_search.exceptions import (
                DuckDuckGoSearchException,
                RatelimitException
            )
        except ImportError:
            error_msg = "duckduckgo-search library not installed. Please add it to requirements."
            logger.error(error_msg)
            return [{"title": "System Error", "url": "", "snippet": error_msg}]

        last_exception = None
        backoff = self.INITIAL_BACKOFF_SECONDS

        for attempt in range(self.MAX_RETRIES):
            try:
                results = []
                # Use the context manager for DDGS
                with DDGS() as ddgs:
                    ddgs_results = ddgs.text(keywords=query, max_results=max_results)

                    if ddgs_results:
                        for r in ddgs_results:
                            results.append({
                                "title": r.get("title", "No Title"),
                                "url": r.get("href", ""),
                                "snippet": r.get("body", "No snippet available.")
                            })

                if not results:
                    return [{
                        "title": "No Results",
                        "url": "",
                        "snippet": f"No results found for query: {query}"
                    }]

                return results

            except RatelimitException as e:
                last_exception = e
                logger.warning(
                    f"DuckDuckGo rate limited (attempt {attempt + 1}/{self.MAX_RETRIES}). "
                    f"Waiting {backoff:.1f}s before retry..."
                )
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(backoff)
                    backoff *= self.BACKOFF_MULTIPLIER

            except DuckDuckGoSearchException as e:
                # Check if this is a rate limit wrapped in generic exception
                error_str = str(e).lower()
                if "ratelimit" in error_str or "202" in error_str:
                    last_exception = e
                    logger.warning(
                        f"DuckDuckGo rate limited (attempt {attempt + 1}/{self.MAX_RETRIES}). "
                        f"Waiting {backoff:.1f}s before retry..."
                    )
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(backoff)
                        backoff *= self.BACKOFF_MULTIPLIER
                else:
                    # Non-retryable search exception
                    logger.error(f"DuckDuckGo search failed: {e}")
                    return [{
                        "title": "Search Error",
                        "url": "",
                        "snippet": f"Search service error: {str(e)}"
                    }]

            except Exception as e:
                logger.error(f"DuckDuckGo search failed with unexpected error: {e}")
                return [{
                    "title": "Search Error",
                    "url": "",
                    "snippet": f"An error occurred during search: {str(e)}"
                }]

        # All retries exhausted due to rate limiting
        logger.error(
            f"DuckDuckGo search failed after {self.MAX_RETRIES} attempts due to rate limiting"
        )
        return [{
            "title": "Rate Limited",
            "url": "",
            "snippet": (
                f"Search service is temporarily rate limited. "
                f"Query '{query}' could not be completed. Please try again later."
            )
        }]
