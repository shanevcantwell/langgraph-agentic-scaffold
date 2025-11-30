import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt
from ..strategies.search.base import BaseSearchStrategy, SearchRequest

logger = logging.getLogger(__name__)

class SearchQuery(BaseModel):
    query: str = Field(..., description="The search query")
    max_results: int = Field(5, description="Max results to return")

class ResearcherSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any], search_strategy: Optional[BaseSearchStrategy] = None):
        super().__init__(specialist_name, specialist_config)
        self.search_strategy = search_strategy
        if self.search_strategy:
            logger.info(f"ResearcherSpecialist initialized with strategy: {self.search_strategy.__class__.__name__}")
        else:
            logger.warning("ResearcherSpecialist initialized WITHOUT a search strategy. Search will fail.")

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
            error_msg = "No search strategy configured for ResearcherSpecialist."
            logger.error(error_msg)
            return [{"title": "Configuration Error", "url": "", "snippet": error_msg}]

        request = SearchRequest(query=query, max_results=max_results)
        return self.search_strategy.execute(request)

    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        if not self.llm_adapter:
            raise ValueError(f"LLM Adapter not attached to {self.specialist_name}")

        messages = state.get("messages", [])
        if not messages:
            return {}
            
        # 1. Load Prompt
        prompt_file = self.specialist_config.get("prompt_file")
        if prompt_file:
            try:
                system_prompt = load_prompt(prompt_file)
            except Exception:
                system_prompt = "You are a Researcher. Search for information to answer the user's request."
        else:
            system_prompt = "You are a Researcher. Search for information to answer the user's request."

        # 2. Create Request with Search Tool
        image_data = state.get("artifacts", {}).get("uploaded_image.png")
        
        request = StandardizedLLMRequest(
            messages=[SystemMessage(content=system_prompt)] + messages,
            tools=[SearchQuery],
            force_tool_call=True,
            image_data=image_data
        )

        # 3. Invoke LLM to get search query
        try:
            response_data = self.llm_adapter.invoke(request)
            tool_calls = response_data.get("tool_calls", [])
            
            search_results = []
            if tool_calls:
                for call in tool_calls:
                    if call['name'] == 'SearchQuery':
                        args = call['args']
                        query = args.get('query')
                        results = self._perform_search(query)
                        search_results.extend(results)
            
            # 4. Return results as artifact
            return {
                "artifacts": {
                    "search_results": search_results
                },
                "scratchpad": {
                    "research_summary": f"Found {len(search_results)} results."
                }
            }

        except Exception as e:
            logger.error(f"Error in Researcher: {e}", exc_info=True)
            return {"error": str(e)}
