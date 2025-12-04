"""
Fallback search strategy that chains multiple search providers.

Tries each provider in order, falling back to the next on failure.
This provides resilience against rate limiting and service outages.
"""
import logging
from typing import List, Dict, Any, Optional

from .base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)

# Error titles that indicate a retryable failure
RETRYABLE_ERRORS = {
    "Rate Limited",
    "Search Error",
    "Timeout Error",
    "Quota Exceeded",
}


class FallbackSearchStrategy(BaseSearchStrategy):
    """
    Search strategy that chains multiple providers with automatic fallback.

    Tries each strategy in order until one succeeds. A strategy is considered
    failed if it returns a single result with a title in RETRYABLE_ERRORS.

    Example usage:
        from app.src.strategies.search.duckduckgo_strategy import DuckDuckGoSearchStrategy
        from app.src.strategies.search.brave_strategy import BraveSearchStrategy

        strategy = FallbackSearchStrategy([
            DuckDuckGoSearchStrategy(),  # Free, try first
            BraveSearchStrategy(),        # Fallback with API key
        ])

        results = strategy.execute(SearchRequest(query="python tutorials"))
    """

    def __init__(self, strategies: List[BaseSearchStrategy]):
        """
        Initialize with ordered list of strategies to try.

        Args:
            strategies: List of search strategies in priority order.
                        First strategy is tried first.
        """
        if not strategies:
            raise ValueError("At least one search strategy is required")

        self.strategies = strategies

    def execute(self, request: SearchRequest) -> List[Dict[str, str]]:
        """
        Execute search with automatic fallback.

        Tries each strategy in order until one returns valid results.

        Args:
            request: SearchRequest with query and max_results

        Returns:
            Results from first successful strategy, or last error if all fail
        """
        last_error_result = None

        for i, strategy in enumerate(self.strategies):
            strategy_name = type(strategy).__name__
            logger.info(
                f"FallbackSearchStrategy: Trying {strategy_name} "
                f"({i + 1}/{len(self.strategies)})"
            )

            try:
                results = strategy.execute(request)

                # Check if this is a retryable error
                if self._is_retryable_error(results):
                    error_title = results[0]["title"] if results else "Unknown"
                    logger.warning(
                        f"FallbackSearchStrategy: {strategy_name} returned "
                        f"retryable error: {error_title}"
                    )
                    last_error_result = results
                    continue

                # Success! Return results
                logger.info(
                    f"FallbackSearchStrategy: {strategy_name} succeeded "
                    f"with {len(results)} results"
                )
                return results

            except Exception as e:
                logger.error(
                    f"FallbackSearchStrategy: {strategy_name} raised exception: {e}"
                )
                last_error_result = [{
                    "title": "Search Error",
                    "url": "",
                    "snippet": f"{strategy_name} failed: {str(e)}"
                }]
                continue

        # All strategies failed
        logger.error(
            f"FallbackSearchStrategy: All {len(self.strategies)} strategies failed"
        )

        if last_error_result:
            # Return the last error for context
            return last_error_result

        return [{
            "title": "Search Error",
            "url": "",
            "snippet": "All search providers failed. Please try again later."
        }]

    def _is_retryable_error(self, results: List[Dict[str, str]]) -> bool:
        """
        Check if results indicate a retryable error.

        A retryable error is a single result with a known error title.
        """
        if len(results) != 1:
            return False

        title = results[0].get("title", "")
        return title in RETRYABLE_ERRORS

    def add_strategy(self, strategy: BaseSearchStrategy, priority: int = -1):
        """
        Add a strategy at the specified priority.

        Args:
            strategy: Search strategy to add
            priority: Index to insert at (-1 = append to end)
        """
        if priority == -1:
            self.strategies.append(strategy)
        else:
            self.strategies.insert(priority, strategy)
