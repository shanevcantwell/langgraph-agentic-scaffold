import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from .base import BaseSpecialist
from ..llm.adapter import StandardizedLLMRequest

logger = logging.getLogger(__name__)

class ResearchPlan(BaseModel):
    search_queries: List[str] = Field(..., description="List of search queries to execute")
    required_information: List[str] = Field(..., description="List of specific information points to extract")

class ResearchOrchestrator(BaseSpecialist):
    """
    Coordinates the Deep Research pipeline.
    Executes Search -> Browse -> Judge -> Synthesize loop.
    """
    
    def _execute_logic(self, state: dict) -> Dict[str, Any]:
        scratchpad = state.get("scratchpad", {})
        research_goal = scratchpad.get("research_goal")
        
        if not research_goal:
            return {"error": "No research_goal provided"}
            
        logger.info(f"Starting research for goal: {research_goal}")
        
        # 1. Plan
        plan = self._generate_plan(research_goal)
        logger.info(f"Generated plan: {plan}")
        
        results = []
        
        # 2. Execute Search
        for query in plan.search_queries:
            logger.info(f"Searching for: {query}")
            try:
                search_results = self.mcp_client.call("web_specialist", "search", query=query, max_results=3)
            except Exception as e:
                logger.error(f"Search failed for query '{query}': {e}")
                continue
            
            for result in search_results:
                url = result.get("url")
                if not url: continue
                
                # 3. Browse
                logger.info(f"Browsing: {url}")
                try:
                    browse_result = self.mcp_client.call("browse_specialist", "browse", url=url)
                except Exception as e:
                    logger.error(f"Browse failed for url '{url}': {e}")
                    continue

                content = browse_result.get("content", "")
                
                if not content: continue
                
                # 4. Judge Relevance
                logger.info(f"Judging relevance for: {url}")
                try:
                    judgment = self.mcp_client.call("inference_service", "judge_relevance", query=research_goal, content=content)
                except Exception as e:
                    logger.error(f"Judgment failed for url '{url}': {e}")
                    continue
                
                if judgment.get("is_relevant"):
                    logger.info(f"Relevant content found: {url}")
                    results.append({
                        "url": url,
                        "content": content,
                        "reasoning": judgment.get("reasoning")
                    })
                else:
                    logger.info(f"Content not relevant: {url}")
                    
        # 5. Synthesize (Simple version for now)
        # In a real implementation, we might route to SynthesizerSpecialist
        # But for now, let's just return the gathered data
        
        return {
            "research_results": results,
            "status": "completed"
        }

    def _generate_plan(self, goal: str) -> ResearchPlan:
        prompt = f"""
        Task: Generate a research plan for the following goal.
        
        Goal: {goal}
        
        Return a JSON object with:
        - search_queries: List[str]
        - required_information: List[str]
        """
        
        request = StandardizedLLMRequest(
            messages=[HumanMessage(content=prompt)],
            output_model_class=ResearchPlan
        )
        
        response = self.llm_adapter.invoke(request)
        return response.get("json_response")
