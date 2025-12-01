import logging
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from .base import BaseSpecialist
from ..strategies.search.base import BaseSearchStrategy, SearchRequest
from ..interface.system_plan import SystemPlan, ExecutionStatus

logger = logging.getLogger(__name__)

class WebSpecialist(BaseSpecialist):
    """
    The 'Hands' of the Deep Research architecture.
    A pure primitive that executes web-related tasks (Search, Browse)
    defined in a SystemPlan. It has NO internal LLM loop.
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


# TODO: The following implementation is a "hidden power" for a specialist. These needs to work agentically
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        """
        Executes the current step in the SystemPlan.
        Returns the raw result. Does NOT update the SystemPlan status.
        """
        artifacts = state.get("artifacts", {})
        plan_data = artifacts.get("system_plan")
        
        if not plan_data:
            logger.error("WebSpecialist executed but no 'system_plan' found in artifacts.")
            return {"error": "No SystemPlan found."}

        try:
            # Load the plan just to read parameters
            plan = SystemPlan(**plan_data)
            current_step = plan.get_current_step()
            
            if not current_step:
                logger.error("WebSpecialist executed but no current step found in SystemPlan.")
                return {"error": "No current step in SystemPlan."}
            
            logger.info(f"WebSpecialist executing Step {current_step.step_number}: {current_step.capability}")
            
            # Execute based on capability
            if current_step.capability == "search":
                query = current_step.params.get("query")
                if not query:
                    return {"error": "Missing 'query' parameter for search."}
                
                # Execute Search Strategy
                results = self._perform_search(query)
                return {"search_results": results}
            
            elif current_step.capability == "browse":
                # Placeholder for Phase 2
                return {"error": "Browse capability not yet implemented."}
            
            else:
                return {"error": f"Unknown capability: {current_step.capability}"}

        except ValidationError as e:
            logger.error(f"Failed to parse SystemPlan: {e}")
            return {"error": f"Invalid SystemPlan: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error in WebSpecialist: {e}", exc_info=True)
            raise # Let NodeExecutor catch it
