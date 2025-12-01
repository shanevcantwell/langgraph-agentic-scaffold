import logging
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from .base import BaseSpecialist
from ..strategies.search.base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)

class WebSpecialist(BaseSpecialist):
    """
    The execution primitive of the Deep Research architecture.
    A pure worker that executes web-related tasks (Search, Browse).
    It has NO internal LLM loop and NO knowledge of SystemPlans.
    It expects a 'web_task' in the scratchpad.
    """
    
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any], search_strategy: Optional[BaseSearchStrategy] = None):
        super().__init__(specialist_name, specialist_config)
        self.search_strategy = search_strategy
        if self.search_strategy:
            logger.info(f"WebSpecialist initialized with strategy: {self.search_strategy.__class__.__name__}")
        else:
            logger.warning("WebSpecialist initialized WITHOUT a search strategy. Search will fail.")

    def register_mcp_services(self, registry):
        """Expose search capability via MCP."""
        registry.register_service(self.specialist_name, {
            "search": self._perform_search
        })

    def _perform_search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Executes a web search using the injected strategy.
        """
        if not self.search_strategy:
            error_msg = "No search strategy configured for WebSpecialist."
            logger.error(error_msg)
            return [{"title": "Configuration Error", "url": "", "snippet": error_msg}]

        request = SearchRequest(query=query, max_results=max_results)
        return self.search_strategy.execute(request)


    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Executes a web task defined in the scratchpad.
        Expected format: state['scratchpad']['web_task'] = {'capability': 'search', 'params': {'query': '...'}}
        """
        scratchpad = state.get("scratchpad", {})
        task = scratchpad.get("web_task")
        
        if not task:
            logger.warning("WebSpecialist executed but no 'web_task' found in scratchpad.")
            return {"error": "No web_task found in scratchpad."}

        try:
            capability = task.get("capability")
            params = task.get("params", {})
            
            logger.info(f"WebSpecialist executing capability: {capability}")
            
            if capability == "search":
                query = params.get("query")
                if not query:
                    return {"error": "Missing 'query' parameter for search."}
                
                # Execute Search Strategy
                results = self._perform_search(query)
                return {"search_results": results}
            
            elif capability == "browse":
                # Placeholder for Phase 2
                return {"error": "Browse capability not yet implemented."}
            
            else:
                return {"error": f"Unknown capability: {capability}"}

        except Exception as e:
            logger.error(f"Unexpected error in WebSpecialist: {e}", exc_info=True)
            raise # Let NodeExecutor catch it
