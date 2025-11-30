import logging
from typing import List, Dict, Any
from .base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)

class DuckDuckGoSearchStrategy(BaseSearchStrategy):
    """
    Concrete implementation of BaseSearchStrategy using DuckDuckGo.
    """

    def execute(self, request: SearchRequest) -> List[Dict[str, str]]:
        """
        Executes a web search using DuckDuckGo.
        """
        query = request.query
        max_results = request.max_results
        logger.info(f"DuckDuckGoSearchStrategy executing search for: '{query}'")
        
        try:
            # Lazy import to avoid hard dependency if not installed
            from duckduckgo_search import DDGS
            
            results = []
            # Use the context manager for DDGS
            with DDGS() as ddgs:
                # ddgs.text returns an iterator of results
                # keywords: query
                # max_results: limit
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

        except ImportError:
            error_msg = "duckduckgo-search library not installed. Please add it to requirements."
            logger.error(error_msg)
            return [{"title": "System Error", "url": "", "snippet": error_msg}]
            
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return [{"title": "Search Error", "url": "", "snippet": f"An error occurred during search: {str(e)}"}]
