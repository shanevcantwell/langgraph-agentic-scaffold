import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest
from ..utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

class SearchQuery(BaseModel):
    query: str = Field(..., description="The search query")
    max_results: int = Field(5, description="Max results to return")

class ResearcherSpecialist(BaseSpecialist):
    def __init__(self, specialist_name: str, specialist_config: Dict[str, Any]):
        super().__init__(specialist_name, specialist_config)
        # LLM adapter is injected by GraphBuilder

    def register_mcp_services(self, registry):
        """Expose search capability via MCP."""
        registry.register_service(self.specialist_name, {
            "search": self._perform_search
        })

    def _perform_search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Executes a web search.
        Currently a MOCK implementation.
        TODO: Integrate real search tool (Tavily, DuckDuckGo, etc.)
        """
        logger.info(f"Researcher performing search for: '{query}'")
        
        # Mock results
        return [
            {
                "title": f"Search Result 1 for '{query}'",
                "url": "https://example.com/result1",
                "snippet": f"This is a simulated search result for the query '{query}'. It contains relevant information."
            },
            {
                "title": f"Search Result 2 for '{query}'",
                "url": "https://example.com/result2",
                "snippet": f"Another simulated result with more details about '{query}'."
            }
        ]

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
