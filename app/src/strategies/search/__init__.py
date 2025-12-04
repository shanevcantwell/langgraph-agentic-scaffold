"""
Search strategies for web search functionality.

Available strategies:
- DuckDuckGoSearchStrategy: Free, no API key, but rate limited
- BraveSearchStrategy: Requires API key, 2000 free/month, no rate limiting
- FallbackSearchStrategy: Chains multiple strategies with automatic fallback

Typical usage:
    from app.src.strategies.search import (
        DuckDuckGoSearchStrategy,
        BraveSearchStrategy,
        FallbackSearchStrategy,
        SearchRequest
    )

    # Simple: single provider
    strategy = DuckDuckGoSearchStrategy()

    # Robust: fallback chain
    strategy = FallbackSearchStrategy([
        DuckDuckGoSearchStrategy(),
        BraveSearchStrategy(),
    ])

    results = strategy.execute(SearchRequest(query="python tutorials"))
"""
from .base import BaseSearchStrategy, SearchRequest
from .duckduckgo_strategy import DuckDuckGoSearchStrategy
from .brave_strategy import BraveSearchStrategy
from .fallback_strategy import FallbackSearchStrategy

__all__ = [
    "BaseSearchStrategy",
    "SearchRequest",
    "DuckDuckGoSearchStrategy",
    "BraveSearchStrategy",
    "FallbackSearchStrategy",
]
